from rocker.restclient import Request

import json
import sys

# Slim wrapper around RestClient with the default url set
class DockerClient:
	# DockerClient constructor
	#
	# The URL can be either a UNIX socket or an HTTP/HTTPS server address, e.g:
	#
	# - unix:///var/run/docker.sock <- that's the default value
	# - http://localhost:1234/
	# - https://localhost:1235/
	#
	#
	# - There are no default ports for HTTP/S sockets
	# - HTTP/S URLs will only be parsed for their host and port, the path
	#   and all other components will be ignored
	# - UNIX socket URLs will however ignore everything except the path part.
	def __init__(self, url = 'unix:///var/run/docker.sock'):
		self._url = url

	# Returns a new RestClient instance pointing to the URL given in the constructor
	def createRequest(self):
		try:
			return Request(self._url)
		except PermissionError as e:
			raise PermissionError("Couln't connect to docker at {0}".format(self._url))

	def printDockerOutput(self, httpResponse):
		while True:
			chunk = httpResponse.readChunk()
			if chunk == None:
				break
			chunk = json.loads(chunk)

			if 'stream' in chunk:
				sys.stdout.write(chunk['stream'])
			else:
				print(":: {0}".format(chunk))
