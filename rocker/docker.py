from rocker.restclient import Request

import json
import os
import sys

# Source: https://svn.blender.org/svnroot/bf-blender/trunk/blender/build_files/scons/tools/bcolors.py
# TODO Maybe use a library to do that
class Col:
	HEADER = '\033[95m'
	OKBLUE = '\033[94m'
	OKGREEN = '\033[92m'
	WARNING = '\033[93m'
	FAIL = '\033[91m'
	ENDC = '\033[0m'
	BOLD = '\033[1m'
	UNDERLINE = '\033[4m'

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
	#def __init__(self, url = 'unix:///var/run/docker.sock'):
	def __init__(self, url = None):
		if url == None:
			# use DOCKER_HOST env var or fallback to default
			url = os.getenv('DOCKER_HOST')

		if url == None:
			url = 'unix:///var/run/docker.sock'

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
			self.printDockerMessage(chunk)

	def printDockerMessage(self, msgJson):
		if 'error' in msgJson:
			print(Col.FAIL, msgJson['error'], Col.ENDC)
		elif 'status' in msgJson:
			print(Col.OKBLUE, msgJson['status'], Col.ENDC)
		elif 'stream' in msgJson:
			sys.stdout.write(msgJson['stream'])
		else:
			print(":: {0}".format(msgJson))

