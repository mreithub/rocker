
from io import BytesIO
from rocker.rocker import Rocker
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
		self.tagPath = os.path.join(path, '.rockerBuild')
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
			with open(self.tagPath, 'w') as f:
				pass
		os.utime(self.tagPath, (self.dataMtime, self.dataMtime))

	# returns the mtime of the newest file in path
	def _findNewestFile(self, path):
		rc = 0 # os.path.getmtime(path)

		for f in os.listdir(path):
			f = os.path.join(path, f)
			mtime = os.path.getmtime(f)
			if os.path.isdir(f):
				mtime = max(self._findNewestFile(f), mtime)

			if mtime > rc:
				rc = mtime
		return rc


# build an image if necessary
#
# This function maintains an empty .rockerBuild file in the image path
# whose mtime will be set to that of the newest file in the directory.
#
# This allows us to quickly decide whether an image rebuild is necessary.
# Returns True if the image was built, False if the build was skipped (i.e. nothing changed).
# Will raise exceptions on error.
def build(imagePath, rocker=Rocker()):
	tagFile = TagFile(imagePath)
	skip = True

	dockerFile = parseDockerfile(imagePath)

	if dockerFile.parent != None:
		if existsInProject(dockerFile.parent):
			if build(dockerFile.parent):
				# always rebuild the image if its parent was rebuilt
				skip = False

	imgInfo = inspect(imagePath)

	# If docker doesn't have the image, build it even if there's a .rockerBuild file
	if imgInfo == None:
		skip = False # always build if docker doesn't know about the image
	if not tagFile.check():
		skip = False # .rockerBuild file is older than the dir's contents

	if not skip:
		rocker.info("Building image: {0}".format(imagePath))

		# initiate build
		with rocker.createRequest().doPost('/build?rm=1&t={0}'.format(imagePath)) as req:
			req.enableChunkedMode()
			tar = tarfile.open(mode='w', fileobj=req)
			_fillTar(tar, imagePath)
			resp = req.send()
			rocker.printDockerOutput(resp)

		# update mtime
		tagFile.update()
	else:
		rocker.debug(1, "Skipping image '{0}' - nothing changed\n".format(imagePath), duplicateId=(imagePath,'build'))

	return not skip


# Returns whether or not the given image exists locally
def exists(imageName, rocker=Rocker()):
	return inspect(imageName, rocker) != None

def existsInProject(imageName):
	return os.path.isfile(os.path.join(imageName, 'Dockerfile'))

# Returns detailed information about the given image (or None if not found)
def inspect(imageName, rocker=Rocker()):
	rc = None

	with rocker.createRequest() as req:
		try:
			rc = Image(req.doGet('/images/{0}/json'.format(imageName)).send().getObject())

		except HttpResponseError as e:
			if e.getCode() == 404:
				pass # return None
			else:
				raise e
	return rc

# Returns a list of all local docker images
def list(rocker=Rocker()):
	rc = []
	with rocker.createRequest() as req:
		for data in req.doGet('/images/json').send():
			rc.append(Image(data))
	return rc

# Parses (parts of) a Dockerfile and returns an Image instance
#
# right now we only extract very little information from the Dockerfile.
# The main purpose for this method is to figure out the source image for this one
# (to be able to build it if necessary)
def parseDockerfile(path):
	# We can handle both the path to the dockerfile as well as its parent directory
	if os.path.exists(os.path.join(path, 'Dockerfile')):
		path = os.path.join(path, 'Dockerfile')

	parentImage = None

	with open(path, 'r') as f:
		for line in f.readlines():
			line = line.strip()
			if len(line) == 0:
				continue
			line = line.split(maxsplit=1)
			if line[0] == 'FROM':
				parentImage = line[1]

	return Image({
		'Parent': parentImage
	})

def pull(name, rocker=Rocker()):
	with rocker.createRequest() as req:
		resp = req.doPost('/images/create?fromImage={0}%3Alatest'.format(name)).send(data=None)
		rocker.printDockerOutput(resp)

# Adds all files in a directory to the specified tarfile object
# 
# This method will use tgtPath as root directory (i.e. strip away unnecessary path parts).
# If tgtPath is a symlink to a directory containing a Dockerfile, _fillTar() will use that
# directory instead (instead of simply adding the symlink)
def _fillTar(tar, tgtPath):
	if not os.path.isfile(os.path.join(tgtPath, "Dockerfile")):
		raise Exception("No Dockerfile in target path '{0}'")

	while os.path.islink(tgtPath):
		tgtPath = os.path.join(os.path.dirname(tgtPath), os.readlink(tgtPath))
		#print("resolved symlink:", tgtPath)

	__fillTar(tar, tgtPath, '')

def __fillTar(tar, dir, prefix):
	for f in os.listdir(dir):
		realPath = os.path.join(dir, f)
		arcPath = os.path.join(prefix, f)
		if os.path.isdir(realPath):
			__fillTar(tar, realPath, arcPath)
		else:
			#print("{0} -> {1}".format(realPath, arcPath))
			tar.add(realPath, arcname=arcPath)