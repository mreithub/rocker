import json
import select
import socket
import urllib.parse

# Slim internal HTTP client written directly on top of the UNIX socket API.
# Therefore it can be used with both UNIX and TCP sockets.
#
# Right now the implementation is pretty much minimal, but new features will be
# added when necessary.
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
# Note for extending RestClient: RestClient manages a small readahead buffer
# which it uses to implement __readLine(). So always use __read() when reading
# from the socket.
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
		self._buffer = None
		self._status = None
		self._statusMsg = None
		self._headers = None # response headers
		self._headerKeys = None # Maps lower case header names to the case sensitive ones


		if url.scheme == 'unix':
			self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
			self._sock.connect(url.path)
		elif url.scheme in ['http', 'https']:
			raise Exception("Not yet implemented: {0}".format(url))
			self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self._sock.create_connection()
		else:
			raise Exception("Unsupported schema: {0}".format(url.schema))

		self._sock.setblocking(0)

	# 'in' operator.
	# This method will return true if a header with the given name exists
	# (case insensitive).
	# Use it like follows:
	#
	# if 'Content-Type' in restClient:
	#    contentType = restClient.getHeader('Content-Type')
	def __contains__(self, key):
		if self._headerKeys == None:
			raise Exception("Headers haven't been read yet!")
		else:
			return key.lower() in self._headerKeys


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

	# Internal read command. Reads at most <length> bytes from the socket.
	# If no bytes are currently available, an empty result will be returned.
	#
	# This method maintains a readahead buffer (you can 'undo' reads calling
	# the __unread() method) which is necessary for __readLine() to work
	# properly.
	def __read(self, length):
		rc = bytes()
		if self._buffer != None:
			rc = self._buffer
			length -= len(rc)
			self._buffer = None

		if length > 0:
			if self.__wait(0):
				rc += self._sock.recv(length)

		return rc

	# Parses the response headers (and returns them)
	#
	# The header data will be stored in self._headers, so subsequent calls
	# to __readHeaders() will simply return the cached data.
	def __readHeaders(self):
		rc = {}

		if self._headers != None:
			return self._headers

		while True:
			line = self.__readLine().strip()
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
					key = line[:colonPos].strip()
					value = line[colonPos+1:].strip()
					rc[key] = value

		self._headers = rc

		# fill _headerKeys (which allows case-insensitive header lookup)
		self._headerKeys = {}
		for key in rc.keys():
			self._headerKeys[key.lower()] = key

		if self._status not in [200, 201]:
			# read data
			data = None
			if b'content-length' in self:
				dataLen = int(self.getHeader(b'content-length'))
				data = self.__read(dataLen)
			else:
				data = self._headers

			raise HttpResponseError(self._statusMsg, self._status, data)

		return rc

	# Reads and returns one line of data from the socket.
	#
	# This method is used by __readHeaders() to simplify header parsing.
	# it invokes __read() until a newline is found and then calls __unread()
	# to push the extra data onto the readahead buffer.
	def __readLine(self):
		buff = []

		while True:
			data = self.__read(128)
			nlPos = data.find(b'\n')
			if nlPos >= 0:
				# we've found a newline, unread everything after it
				self.__unread(data[nlPos+1:])
				buff.append(data[:nlPos])
				break
			else:
				buff.append(data)

		buff = b''.join(buff)

		if buff.endswith(b'\r'):
			buff = buff[:-1]

		return buff

	# sends an HTTP request to the server (using the method specified)
	#
	# If the response's content type indicates JSON data, it will be
	# deserialized (using json.loads())
	def __run(self, method, path, data=None):
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

		self.__readHeaders()
		respLen = 0
		if b'Content-length' in self:
			respLen = int(self.getHeader(b'Content-Length'))
			#raise Exception("Missing Content-Length in Docker response!")
		if b'Content-Type' not in self:
			raise Exception("Missing Content-Type header in Docker response!")

		respType = self.getHeader(b'Content-Type')

		rc = self.__read(respLen)

		if respType.lower().split(b';')[0] == b'application/json':
			rc = json.loads(str(rc, 'utf8'))
		else:
			raise Exception("Expected JSON data, but got '{0}'".format(respType))

		return rc

	# Push data onto the readahead buffer (which is checked by __read())
	def __unread(self, data):
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
	# This method uses select.select() internally. For a timeout of 0,
	# __wait() will return immediately.
	def __wait(self, timeout=2):
		inputs,_,_ = select.select([self._sock], [], [], timeout)
		return len(inputs) > 0

	# Initiate an HTTP GET request to the given path
	def doGet(self, path):
		return self.__run('GET', path)

	# Initiate an HTTP POST request to the given path (and sending the data)
	def doPost(self, path, data):
		return self.__run('POST', path, data)

	# Get a response header
	def getHeader(self, key):
		key = key.lower()
		if self._headers == None:
			raise Exception("Headers haven't been read yet!")
		elif key not in self._headerKeys:
			raise KeyError("Header not found: {0}".format(key))
		return self._headers[self._headerKeys[key]]

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