import json
import select
import socket
import sys
import time
import urllib.parse

# Slim internal HTTP client written directly on top of the UNIX socket API.
# Therefore it can be used with both UNIX and TCP sockets.
#
# The intent for this module is only to implement a counterpart for docker's
# remote API. It's use should be limited to rocker (as the API might change in
# the future).
#
# Right now the implementation is pretty minimal, but new features will be
# added as needed.
#
# You should create a new RestClient instance for each request (maybe we'll
# implement something like keep-alive sometime in the future, but for now it's
# single-request).
#
# The best way to instantiate the client is using a with statement. That way
# all resources will be released properly. E.g.:
#
# with RestClient("unix:///var/run/docker.sock") as client:
#     response = client.doGet('/version')
#     # do something with the response
#
# TODO split this up into request/response classes
#
# RestClient wraps BufferedReader and ChunkReader around the source socket.
#
class RestClient:
	# RestClient constructor
	#
	# You'll have to provide either a UNIX socket path or a HTTP/HTTPS server
	# URL. For example:
	#
	# unix:///var/run/docker.sock
	# http://dockerHost:1234/
	# https://dockerHost:1234/
	#
	# Note that HTTP and HTTPS aren't implemented yet (feel free to provide a
	# patch/merge request).
	def __init__(self, url):
		url = urllib.parse.urlsplit(url)
		self._status = None
		self._statusMsg = None
		self._reqHeaders = {}
		self._respHeaders = None # response headers
		self._respHeaderKeys = None # Maps lower case header names to the case sensitive ones

		if url.scheme == 'unix':
			sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
			sock.connect(url.path)
		elif url.scheme in ['http', 'https']:
			raise Exception("Not yet implemented: {0}".format(url))
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock.create_connection()
		else:
			raise Exception("Unsupported schema: {0}".format(url.schema))

		sock.setblocking(0)

		self._sock = ChunkReader(BufferedReader(sock))

	# 'in' operator.
	# This method will return true if a header with the given name exists
	# (case insensitive).
	# Use it like follows:
	#
	# if 'Content-Type' in restClient:
	#    contentType = restClient.getHeader('Content-Type')
	def __contains__(self, key):
		if self._respHeaderKeys == None:
			raise Exception("Headers haven't been read yet!")
		else:
			return key.lower() in self._respHeaderKeys


	# 'with' statement implementation
	# simply returns self
	def __enter__(self):
		return self

	# 'with' statement implementation
	# calls close() when the calling code exits the 'with' block
	def __exit__(self, type, value, traceback):
		self.close()

	# Closes the underlying socket
	def close(self):
		self._sock.close()

	def __parseContentType(self):
		# will be something like:
		# - text/plain; charset=utf-8
		# - application/json

		# if no charset is specified, this method will assume ascii data
		# (it's better to raise an exception and be able to fix bugs as they come
		# than to decode the data in a wrong way)
		#
		# JSON however uses a default charset of utf8
		if 'Content-Type' not in self:
			raise Exception("Missing Content-Type header in Docker response!")

		header = self.getHeader('Content-Type')
		cTypeParts = header.split(';')
		cType = cTypeParts[0].strip().lower()
		charset = 'ascii'

		if len(cTypeParts) > 2:
			raise ValueError("Malformed content-type header: {0}".format(header))
		if len(cTypeParts) == 2:
			charsetParts = cTypeParts[1].split('=')
			if len(charsetParts) != 2 or charsetParts[0].lower().strip() != 'charset':
				raise ValueError("Malformed charset declaration: {0}".format(cTypeParts[1]))

			charset = charsetParts[1].strip().lower()
		elif cType == 'application/json': # implicitly: and len(cTypeParts) < 2
			charset = 'utf-8'

		self._contentType = cType
		self._charset = charset


	# Parses the response headers (and returns them)
	#
	# The header data will be stored in self._respHeaders, so subsequent calls
	# to __readHeaders() will simply return the cached data.
	def __readHeaders(self):
		rc = {}

		if self._respHeaders != None:
			return self._respHeaders

		while True:
			line = self._sock.readLine().strip()
			if len(line) == 0:
				break
			else:
				if self._status == None:
					# first line contains the HTTP status (sth like: 'HTTP/1.1 200 Ok')
					firstSpace = line.find(b' ')
					secondSpace = line.find(b' ', firstSpace+1)

					if firstSpace < 0 or secondSpace < 0:
						raise Exception("Malformed response status: {0}".format(line))

					self._status = int(line[firstSpace+1:secondSpace])
					self._statusMsg = line[secondSpace+1:]
				else:
					colonPos = line.find(b':')
					if colonPos < 0:
						raise Exception("Malformed response header line: {0}".format(line))
					key = str(line[:colonPos].strip(), 'ascii')
					value = str(line[colonPos+1:].strip(), 'utf-8')
					rc[key] = value

		self._respHeaders = rc

		# fill _headerKeys (which allows case-insensitive header lookup)
		self._respHeaderKeys = {}
		for key in rc.keys():
			self._respHeaderKeys[key.lower()] = key

		if self._status not in [200, 201]:
			# read data
			data = None
			if 'content-length' in self:
				dataLen = int(self.getHeader('content-length'))
				data = self._sock.recv(dataLen)
			else:
				data = self._respHeaders

			raise HttpResponseError(self._statusMsg, self._status, data)

		return rc

	# sends an HTTP request to the server (using the method specified)
	#
	# If the response's content type indicates JSON data, it will be
	# deserialized (using json.loads())
	def __run(self, method, path, data=None, parseResponse=True):
		# send request
		self._sock.send("{0} {1} HTTP/1.1\r\n".format(method, path).encode('ascii'))
		if data != None:
			if type(data) == dict:
				data = bytes(json.dumps(data), 'utf8')

			# send request headers and data
			self._sock.send("Content-length: {0}\r\n".format(len(data)).encode('ascii'))
			self._sock.send(b"Content-type: application/json\r\n")

		self._sock.send(b'\r\n')

		if data != None:
			self._sock.send(data)

		# parse response headers
		self.__readHeaders()

		respLen = 0
		if 'Content-length' in self:
			respLen = int(self.getHeader('Content-Length'))
			#raise Exception("Missing Content-Length in Docker response!")

		self.__parseContentType()

		if self.isChunked():
				# we've got a response using chunked encoding
			self._sock.enableChunkedMode()
			return None
		else:
			rc = self.read(respLen, blocking=True)
			if len(rc) < respLen:
				raise Exception('only got {0} bytes of response when we were expecting {1}'.format(len(rc), respLen))

			if self._contentType.lower() == 'application/json':
				try:
					return json.loads(rc)
				except ValueError as e:
					# JSON parser error => print data and rethrow exception
					print(path)
					sys.stderr.write("ERROR while parsing JSON data, input:\n{0}\n".format(str(rc, 'utf8')))
					sys.stderr.write("Headers: {0}\n".format(self._respHeaders))
					raise e
			else:
				raise Exception("Expected JSON data, but got '{0}'".format(respType))

	# Initiate an HTTP GET request to the given path
	def doGet(self, path):
		return self.__run('GET', path)

	# Initiate an HTTP POST request to the given path (and sending the data)
	def doPost(self, path, data, parseResponse=True):
		return self.__run('POST', path, data, parseResponse)

	# Get a response header
	def getHeader(self, key):
		key = key.lower()
		if self._respHeaders == None:
			raise Exception("Headers haven't been read yet!")
		elif key not in self._respHeaderKeys:
			raise KeyError("Header not found: {0}".format(key))
		return self._respHeaders[self._respHeaderKeys[key]]

	# Returns True if the server indicated the use of chunked transfer encoding
	# (by setting the respective header)
	#
	# If this method returns True, you need to use readChunk(); read() and readLine() will raise
	# an exception. If it's false, readChunk() throws an exception while the other two will work.
	def isChunked(self):
		if 'Transfer-Encoding' in self:
			if self.getHeader('Transfer-Encoding').lower().strip() == 'chunked':
				return True
		return False

	# Read data from the underlying socket
	#
	# If blocking is set to False (default) count will be the maximum number of bytes to read.
	# If it's true, read() will read exactly count bytes (which means that it might block indefinitely
	# if you expect more data than you'll get).
	#
	# Note: count is in bytes, not characters.
	def read(self, count, blocking=False):
		if not blocking:
			return str(self._sock.recv(count), self._charset)
		else:
			rc = b''
			while count > 0:
				data = self._sock.recv(count)
				count -= len(data)
				rc += data
				if count > 0:
					self._sock.wait(1)
			return str(rc, self._charset)

	# Reads the next response chunk from the underlying socket.
	#
	# This method will only return full chunks and might block to wait for
	# all data to be received.
	#
	# However, if there's no data available at all, it will return an empty
	# result immediately.
	def readChunk(self):
		rc = self._sock.readChunk()
		if rc != None:
			rc = str(rc, self._charset)

		return rc

	def readLine(self):
		return str(self._sock.readLine(), self._charset)

		
class BufferedReader:
	# source is a file-like object
	def __init__(self, source):
		self._source = source
		self._buffer = None

	def close(self):
		self._source.close()

	def enableChunkedMode(self):
		self._source.enableChunkedMode()

	def fileno(self):
		return self._source.fileno()

	# Buffered read command. Reads at most <length> bytes from the socket.
	# If no bytes are currently available, an empty result will be returned.
	# This method won't block.
	#
	# This method maintains a readahead buffer (you can 'undo' reads calling
	# the unrecv() method)
	def recv(self, length):
		rc = bytes()
		if self._buffer != None:
			rc = self._buffer

			if len(rc) > length:
				self._buffer = rc[length:]
				rc = rc[:length]
				length = 0
			else:
				length -= len(rc)
				self._buffer = None

		else:
			if self.wait(2):
				rc += self._source.recv(length)

		return rc


	# Reads and returns one line of data from the socket.
	#
	# This method invokes recv() until a newline is found and then calls unrecv()
	# to push the extra data onto the readahead buffer.
	#
	# It will block until a whole method was read
	def readLine(self):
		buff = []

		while True:
			data = self.recv(128)
			nlPos = data.find(b'\n')
			if nlPos >= 0:
				# we've found a newline, unrecv everything after it
				self.unrecv(data[nlPos+1:])
				buff.append(data[:nlPos])
				break
			else:
				buff.append(data)

		buff = b''.join(buff)

		# strip \r (windows newline)
		if buff.endswith(b'\r'):
			buff = buff[:-1]

		return buff

	def send(self, data):
		self._source.send(data)

	# Push data onto the readahead buffer (which is checked by read())
	def unrecv(self, data):
		if self._buffer != None:
			# append it to the buffer
			self._buffer += data
		else:
			self._buffer = data

	# Wait for data to be available on the socket (or the timeout to elapse)
	#
	# timeout is a float value representing the maximum time to wait in seconds
	#
	# Returns True if there's data to be read, False on timeout
	#
	# This method uses select.select() internally but uses its own timing code.
	# For a timeout of 0 wait() will return immediately.
	def wait(self, timeout=2):
		if self._buffer != None and len(self._buffer) > 0:
			return True

		inputs,_,_ = select.select([self._source.fileno()], [], [], timeout)
		return len(inputs) > 0

class ChunkReader:
	def __init__(self, source):
		self._source = source
		self._chunked = False

	def close(self):
		self._source.close

	def enableChunkedMode(self):
		self._chunked = True

	def fileno(self):
		return self._source.fileno()

	def recv(self, maxLen):
		if not self._chunked:
			# normal un-chunked mode
			return self._source.recv(maxLen)
		else:
			raise IOError("recv() not allowed in chunked mode!")

	def readLine(self):
		if not self._chunked:
			# normal mode => simply pass call to BufferedReader
			return self._source.readLine()
		else:
			raise IOError("readLine() not allowed in chunked mode!")

	# reads a whole chunk of data from the server.
	# If an empty chunk is returned (EOT), this method returns None
	def readChunk(self):
		rc = b''
		if not self._chunked:
			raise IOError("readChunk() can only be used in chunked mode!")

		# read chunk len (format: '0123abc\r\n' - 0123abc being the hexadecimal length of the next chunk)
		# TODO handle lack of data (which should result in readLine returning None)
		length = self._source.readLine()
		length = int(length, 16)

		# read the actual data
		while length > 0:
			# TODO call select()/wait() to avoid busy-waiting
			data = self._source.recv(length)
			length -= len(data)
			rc += data

		# hit the end of a chunk. read \r\n
		foo = self._source.recv(2)
		assert foo == b'\r\n'

		# We'll return None instead of an empty string
		if rc == b'':
			rc = None # indicates EOT

		return rc

	def send(self, data):
		self._source.send(data)

	def wait(self, timeout=2):
		return self._source.wait(timeout)

# Will be raised if the REST server responds with a code other than 200 (Ok)
class HttpResponseError(Exception):
	def __init__(self, message, code, data):
		super(Exception, self).__init__(message)
		self._code = code
		self._data = data

	# Get the HTTP response code
	def getCode(self):
		return self._code

	def getData(self):
		return self._data