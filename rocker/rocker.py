from rocker.restclient import Request

import getopt
import json
import os
import pkg_resources
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

# rocker boilerplate class
class Rocker:
	# Rocker constructor
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
		self._lastMsgId = None
		self._duplicateIDs = set()
		self._verbosity = 0

	# Returns a new RestClient instance pointing to the URL given in the constructor
	def createRequest(self):
		try:
			return Request(self._url)
		except PermissionError as e:
			raise PermissionError("Couln't connect to docker at {0}".format(self._url))

	def getDockerVersion(self):
		return self.createRequest().doGet("/version").send().getObject()

	def getopt(self):
		try:
			opts, args = getopt.gnu_getopt(sys.argv[1:], 'v')

			for opt,_ in opts:
				if opt == '-v':
					self._verbosity += 1

			return args
		except getopt.GetoptError as e:
			self.error(e, exitCode=1)

	def printDockerOutput(self, httpResponse):
		while True:
			chunk = httpResponse.readChunk()
			if chunk == None:
				break
			chunk = json.loads(chunk)
			self.printDockerMessage(chunk)

	# Print Docker status messages (with color coding)
	#
	# This method will print subsequent messages for the same image/container ID in the same line (i.e. overwrite the last message)
	def printDockerMessage(self, msgJson):
		col = None
		msg = None
		newline = '\n'

		if 'id' in msgJson:
			# overwrite lines with the same ID (instead of printing a new one)
			if self._lastMsgId == msgJson['id']:
				# go back one line (and clear it)
				sys.stdout.write('\033[1A\033[K')

			# prepend ID
			sys.stdout.write("{0}: ".format(msgJson['id']))

		# color message depending on type
		if 'error' in msgJson:
			col = Col.FAIL
			msg = msgJson['error']
			newline=''
		elif 'status' in msgJson:
			col = Col.OKBLUE
			msg = msgJson['status']

			if 'progress' in msgJson:
				msg = "{0} {1}".format(msgJson['status'], msgJson['progress'])
		elif 'stream' in msgJson:
			msg = msgJson['stream']
			newline=''

		else:
			msg = ":: {0}".format(msgJson)

		if col != None:
			msg = "{0}{1}{2}".format(col, msg, Col.ENDC)

		sys.stdout.write("{0}{1}".format(msg, newline))

		# update _lastMsgId
		if 'id' in msgJson:
			self._lastMsgId = msgJson['id']
		else:
			self._lastMsgId = None

	def printVersion(self):
		dockerInfo = self.getDockerVersion()
		rockerInfo = pkg_resources.require("rocker")[0]

		print("Rocker version: {v}".format(v=rockerInfo.version))
		print("Docker version: {Version}".format(**dockerInfo))
		self.debug(1, "Docker API version: {ApiVersion}".format(**dockerInfo))
		self.debug(1, "Docker Kernel version: {KernelVersion}".format(**dockerInfo))
		self.debug(2, "Docker GIT revision: {GitCommit}".format(**dockerInfo))
		self.debug(2, "Docker GO version {GoVersion}".format(**dockerInfo))

	def _msg(self, msg, col, duplicateId, stream):
		if duplicateId != None:
			# don't print duplicate messages
			if duplicateId in self._duplicateIDs:
				return
			else:
				self._duplicateIDs.add(duplicateId)

		if col != None:
			msg="{0}{1}{2}".format(col, msg, Col.ENDC)

		stream.write("{0}\n".format(msg))


	def error(self, msg: str, exitCode=None):
		self._msg("ERROR: {0}".format(msg), Col.FAIL, None, sys.stderr)
		if exitCode != None:
			sys.exit(exitCode)

	def info(self, msg: str, duplicateId=None):
		self._msg(msg, Col.OKGREEN, duplicateId, sys.stdout)

	def debug(self, level, msg, duplicateId=None):
		if self._verbosity < level:
			return # too verbose

		self._msg(msg, None, duplicateId, sys.stdout)
