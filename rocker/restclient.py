import codecs
import json
import select
import socket
import sys
import time
import urllib.parse

# Slim HTTP client written directly on top of the UNIX socket API.
# Therefore it can be used with both UNIX and TCP sockets.
#
# Its intended use is  limited to rocker (the restclient API should not be
# considered stable).
#
# Right now the idea is to create a new Request instance for each request.
#
# The best way to instantiate the client is using a with statement. That way
# all resources will be released properly. E.g.:
#
# with Request("unix:///var/run/docker.sock") as req:
#     response = client.doGet('/version').send()
#     # do something with the response
#
# send() will return a Response object which can then be used to act accordingly
class Request:
	# Request constructor
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

		self._headers = {}
		self._headerKeys = {}
		self._chunked = False
		self._headersSent = False
		self._method = None
		self._url = None
		self._reqBodyPos = 0

		self.setHeader("User-agent", "rocker v0.1") # TODO use the real rocker version

		if url.scheme == 'unix':
			sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
			sock.connect(url.path)
		elif url.scheme in ['http', 'https']:
			raise Exception("Not yet implemented: {0}".format(url))
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock.create_connection()
		else:
			raise Exception("Unsupported schema: {0}".format(url.schema))

#		sock.setblocking(0)

		self._sock = ChunkReader(BufferedReader(sock))

	# 'with' statement implementation
	# simply returns self
	def __enter__(self):
		return self

	# 'with' statement implementation
	# calls close() when the calling code exits the 'with' block
	def __exit__(self, type, value, traceback):
		self.close()

	# Sends the HTTP request headers
	#
	# This method makes sure the headers will be sent only once
	def _sendHeaders(self):
		if self._headersSent:
			return

		self._sock.send("{0} {1} HTTP/1.1\r\n".format(self._method, self._url).encode('ascii'))

		for key, value in self._headers.items():
			# for now I'll only allow ASCII headers (file a bug if that's not enough)
			self._sock.send("{0}: {1}\r\n".format(key, value).encode('ascii'))

		self._sock.send(b'\r\n')

		self._headersSent = True

	# Closes the underlying socket
	def close(self):
		self._sock.close()

	# Specifies the url for this GET request
	def doGet(self, url):
		self._method = "GET"
		self._url = url

		return self

	# Specifies the url for this POST request
	def doPost(self, url):
		self._method = "POST"
		self._url = url

		return self

	# Tells Request to use chunked mode
	#
	# You need to call this method before using write().
	# But in chunked mode send() won't accept any request body data.
	#
	# Will fail if the headers have already been sent.
	def enableChunkedMode(self):
		self.setHeader("Transfer-encoding", "chunked")
		self._chunked = True

	# Set a request header
	#
	# Header names are case insensitive (so 'Content-type' will overwrite 'Content-Type', etc.)
	#
	# This method will fail if the headers have been sent already
	def setHeader(self, key, value):
		if self._headersSent:
			raise Exception("Headers already sent!")
		if key.lower() in self._headerKeys:
			# overwrite header
			del self._headers[self._headerKeys[key]]

		self._headers[key] = value
		self._headerKeys[key.lower()] = key

	# Finalizes the request and returns a Response object
	#
	# This method will send the headers if that hasn't happened yet,
	# send data if not in chunked mode and then return a Response
	# object using the underlying socket
	def send(self, data=None):
		if data != None:
			if self._chunked:
				raise Exception("data can't be set when in chunked mode")

			if type(data) == dict:
				data = bytes(json.dumps(data), 'utf8')

			self.setHeader("Content-type", "application/json")
			self.setHeader("Content-length", str(len(data)))
		elif self._chunked:
			# send final chunk
			self._sock.send(b'0\r\n\r\n')

		self._sendHeaders()

		if data != None:
			self._sock.send(data)

		return Response(self._sock)

	# Returns the number of bytes already written in the request body
	#
	# With this method you can use Request as `fileobj` parameter for `tarfile`
	def tell(self):
		return self._reqBodyPos

	# Write request body data in chunked mode
	def write(self, data):
		if not self._chunked:
			raise Exception("Request.write() only works in chunked mode!")

		# make sure we can actually write data
		select.select([], [self._sock], [])

		self._sendHeaders()
		self._sock.send("{0:x}\r\n".format(len(data)).encode('ascii'))
		self._sock.send(data)
		self._sock.send(b"\r\n")
		self._reqBodyPos += len(data)

# Represents a HTTP response
#
# Response objects are created by Request.send().
#
# They will parse the response headers, try to figure out content type and charset
# and give you access to the response body in various forms
class Response:
	# Response constructor (should only be called by Request.send()
	def __init__(self, sock):
		self._sock = ChunkReader(BufferedReader(sock))
		self._headers = None
		self._headerKeys = {}
		self._status = None
		self._statusMsg = None

		self._parseHeaders()

		self.__parseContentType()

		if self.isChunked():
			self._sock.enableChunkedMode()

	# 'in' operator.
	# This method will return true if a response header with the given name exists
	# (case insensitive).
	# Use it like follows:
	#
	# if 'Content-Type' in restClient:
	#    contentType = restClient.getHeader('Content-type')
	def __contains__(self, key):
		if self._headerKeys == None:
			raise Exception("Headers haven't been read yet!")
		else:
			return key.lower() in self._headerKeys

	# Internal method to figure out the response data type and character set
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
			if self._status == 204: # no content
				self._contentType = None
				self._charset = None
			else:
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
	# The header data will be stored in self._headers, so subsequent calls
	# to __readHeaders() will simply return the cached data.
	def _parseHeaders(self):
		rc = {}

		if self._headers != None:
			return self._headers

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

		self._headers = rc

		# fill _headerKeys (which allows case-insensitive header lookup)
		self._headerKeys = {}
		for key in rc.keys():
			self._headerKeys[key.lower()] = key

		if self._status not in [200, 201, 204]:
			# read data
			data = None
			if 'content-length' in self:
				dataLen = int(self.getHeader('content-length'))
				data = self._sock.recv(dataLen)
			else:
				data = self._headers

			raise HttpResponseError(self._statusMsg, self._status, data)

		return rc


	# Get a response header (key is case insensitive)
	#
	# Raises a KeyError if the header wasn't found, so use the `in` operator before calling
	# this method.
	def getHeader(self, key):
		key = key.lower()
		if self._headers == None:
			raise Exception("Headers haven't been read yet!")
		elif key not in self._headerKeys:
			raise KeyError("Header not found: {0}".format(key))
		return self._headers[self._headerKeys[key]]

	# Returns a json decoded response object.
	#
	# if the response was chunked, this method only reads the first chunk (might change if it turns out to be necessary)
	# If it wasn't, readAll() will be used.
	def getObject(self):
		rc = None
		if self.isChunked():
			rc = self.readChunk()
		else:
			rc = self.readAll()
		return json.loads(rc)

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
			return str(self._sock.readExactly(count), self._charset)

	# Reads exactly `content-length` response bytes and decodes them using the detected encoding.
	#
	# This method will only work if the content-length header was specified by the remote server
	# (which won't be the case for chunked responses)
	def readAll(self):
		if self.isChunked():
			raise Exception("readAll() can't be used in chunked mode!")
		count = int(self.getHeader('Content-length'))
		rc = self._sock.readExactly(count)

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

	# Reads the next line from the underlying socket
	def readLine(self):
		return str(self._sock.readLine(), self._charset)

# Wraps around the socket to provide readline() and unrecv()
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

	# Reads exactly length bytes from the socket
	#
	# May block indefinitely
	def readExactly(self, length):
		rc = []
		while length > 0:
			self.wait()
			data = self.recv(length)
			length -= len(data)
			rc.append(data)

		return b''.join(rc)

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

# HTTP chunked response implementation
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

	# reads a whole chunk of data from the server.
	# If an empty chunk is returned (EOT), this method returns None
	def readChunk(self):
		if not self._chunked:
			raise IOError("readChunk() can only be used in chunked mode!")

		# read chunk len (format: '0123abc\r\n' - 0123abc being the hexadecimal length of the next chunk)
		length = self._source.readLine()
		length = int(length, 16)

		# read the actual data
		rc = self._source.readExactly(length)

		# hit the end of a chunk. read \r\n
		chunkEnd = self._source.readExactly(2)
		if chunkEnd != b'\r\n':
			raise Exception("Got invalid chunk end mark: {0} (expected {1})".format(codecs.encode(chunkEnd, 'hex'), codecs.encode(b'\r\n', 'hex')))

		# We'll return None instead of an empty string
		if rc == b'':
			rc = None # indicates EOT

		return rc

	def readExactly(self, length):
		if not self._chunked:
			# normal mode => simply pass call to BufferedReader
			return self._source.readExactly(length)
		else:
			raise IOError("readExactly() not allowed in chunked mode!")

	def readLine(self):
		if not self._chunked:
			# normal mode => simply pass call to BufferedReader
			return self._source.readLine()
		else:
			raise IOError("readLine() not allowed in chunked mode!")

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
