
from io import BytesIO
from rocker.docker import DockerClient
from rocker.restclient import HttpResponseError

import json
import os
import sys
import tarfile

# Data class representing a Docker image
class Image:
	def __init__(self, json):
		self.config = Image._getValue(json, 'ContainerConfig')
		self.created = Image._getValue(json, 'Created')
		self.entrypoint = Image._getValue(json, 'Entrypoint')
		self.id = Image._getValue(json, 'Id');
		self.parent = Image._getValue(json, 'Parent', 'ParentId')
		self.repoTags = Image._getValue(json, 'RepoTags')
		self.size = Image._getValue(json, 'Size')
		self.virtualSize = Image._getValue(json, 'VirtualSize')

		self._otherData = json

	# helper function to extract a value from a map (and just return None if it
	# wasn't there)
	#
	# You can provide more than one key to use, in which case the first one found
	# will be returned
	@staticmethod
	def _getValue(data, *keys):
		rc = None

		for key in keys:
			if key in data:
				rc = data[key]
				del data[key]
				break

		return rc

class TagFile:
	# This method will use _findNewestFile() to get max(mtime) of all the files
	# in path recursively
	def __init__(self, path):
		self.tagPath = os.path.join(path, '.rockerFile')
		self.tagMtime = 0

		if os.path.exists(self.tagPath):
			self.tagMtime = os.path.getmtime(self.tagPath)

		self.dataMtime = self._findNewestFile(path)

	# returns True if the tag file is up to date.
	# If the tag file doesn't exist or is older than the compared files, False
	# will be returned.

	def check(self):
			return self.tagMtime >= self.dataMtime

	# Updates the tagFile's mtime to the mtime of the newest data file
	# The tag file will be created if it doesn't exist
	def update(self):
		if not os.path.exists(self.tagPath):
			sys.utimes(self.tagPath, (self.dataMtime, self.dataMtime))

	# returns the mtime of the newest file in path
	def _findNewestFile(self, path):
		rc = 0 # os.path.getmtime(path)

		for f in os.listdir(path):
			f = os.path.join(path, f)
			mtime = os.path.getmtime(f)
			if os.path.isdir(f):
				mtime = max(self.findNewestFile(f), mtime)

			if mtime > rc:
				rc = mtime
		return rc


# build an image if necessary
#
# This function maintains an empty .rockerBuild file in the image path
# whose mtime will be set to that of the newest file in the directory.
#
# This allows us to quickly decide whether an image rebuild is necessary.
def build(imagePath, docker=DockerClient()):
	tagFile = TagFile(imagePath)

	if tagFile.check():
		# nothing seems to have changed => skip building this image
		sys.stderr.write("Not building image '{0}' - nothing changed\n".format(image))
		return

	# generate TAR file (will be held in RAM currently. Maybe there's a 
	# way to really 'stream' it (i.e. only keep small chunks in memory)
	stream = BytesIO()
	tar = tarfile.open(mode='w', fileobj=stream)

	tar.add(imagePath)

	# inituate build
	with docker.createClient() as c:
		c.doPost('/image/create', stream.getvalue())

	# update mtime
	tagFile.update()

# Returns whether or not the given image exists locally
def exists(imageName, docker=DockerClient()):
	return inspect(imageName, docker) != None

# Returns detailed information about the given image (or None if not found)
def inspect(imageName, docker=DockerClient()):
	rc = None

	with docker.createClient() as c:
		try:
			rc = c.doGet('/images/{0}/json'.format(imageName))

			if rc == None:
				# got a chunked response
				rc = json.loads(c.readChunk())

			rc = Image(rc)

		except HttpResponseError as e:
			if e.getCode() == 404:
				pass # return None
			else:
				raise e
	return rc

# Returns a list of all local docker images
def list(docker=DockerClient()):
	rc = []
	with docker.createClient() as c:
		for data in c.doGet('/images/json'):
			rc.append(Image(data))
	return rc

def pull(name, docker=DockerClient()):
	with docker.createClient() as c:
		c.doPost('/images/create?fromImage={0}'.format(name), data=None, parseResponse=False)
		while True:
			chunk = c.readChunk()
			if chunk == None:
				break
			print(":: {0}".format(chunk))

def _findNewestFile():
	# TODO implement me
	raise Exception("Not yet implemented!!!")
