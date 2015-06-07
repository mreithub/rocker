from rocker import image
from rocker.docker import DockerClient
from rocker.restclient import HttpResponseError

import json
import os
import sys

# data class representing a Docker container
class Container:
	def __init__(self, json):
		self.id = json['Id']
		self.image = json['Image']
		self.command = json['Command']
		self.created = json['Created']
		self.status = json['Status']

# Converts .rocker files to the docker API format
class RockerFile:
	def __init__(self, name):
		config = RockerFile._readConfig(name)

		self.depends = {}

		self.name = name
		self.image = RockerFile._getValue(config, 'image', "You need to specify an 'image' for your .rocker container!")

		self.env = RockerFile._getValue(config, 'env')
		self.links = self._parseLinks(config)
		self.ports = RockerFile._getValue(config, 'ports')
		self.raw = RockerFile._getValue(config, 'raw')
		self.volumes = RockerFile._parseVolumes(config, name)
		self.volumesFrom = self._parseVolumesFrom(config)

		# all the remaining keys in data are unsupporyed => issue warnings
		for key in config.keys():
			sys.stderr.write("WARNING: unsupported .rocker key: '{0}'\n".format(key))

	def toApiJson(self):
		rc = {}

		# non-raw entries override raw ones => seed from raw first
		if self.raw != None:
			rc = self.raw;

		rc['Image'] = self.image

		if self.env != None:
			env = []
			for key, value in self.env.items():
				env.append("{0}={1}".format(key, value))
			rc['Env'] = env


		hostConfig = {}
		if self.links != None:
			# convert the {'alias': 'containerName', ...} format to ["containerName:alias"]
			links = []
			
			for alias, containerName in self.links.items():
				links.append("{0}:{1}".format(containerName, alias))
			hostConfig['links'] = links

		rc['HostConfig'] = hostConfig

		return rc

	@staticmethod
	def _getValue(data, key, errMsg=None):
		rc = None
		if key in data:
			rc = data[key]
			del data[key]
		elif errMsg != None:
			raise KeyError(errMsg)
		return rc

	@staticmethod
	def _mkdirs(path):
		if not os.path.isdir(path):
			os.makedirs(path)

	def _parseLinks(self, config):
		rc = None

		if 'links' in config:
			# we want links to be in the format {"alias": "containerName", ...}
			links = RockerFile._getValue(config, 'links')
			if type(links) == list: # [ "containerName:alias", ... ]
				# parse each item and add them to the list
				realLinks = {}
				for v in links:
					v = v.split(':', maxsplit=1)
					if len(v) == 1:
						v.append(v[0]) # duplicate item
					realLinks[v[1]] == v[0]
				rc = realLinks

			elif type(links) == dict: # { alias: containerName, ... }
				rc = links
			else:
				raise ValueError("Unsupported 'links' type: '{0}'".format(type(links)))

			# add links to dependencies (to be able to (re-)build them if necessary)
			for container in rc.values():
				self.depends[container] = None

		return rc

	@staticmethod
	def _parseVolumes(config, containerName):
		rc = None

		if 'volumes' in config:
			rc = []
			for v in config['volumes']:
				volStr = None
				if type(v) == dict:
					if not 'to' in v:
						raise ValueError("Volume config needs a 'to' field!")
					if 'from' in v:
						# create host directory if necessary
						fromPath = os.path.join('/docker', containerName, v['from'])
						RockerFile._mkdirs(fromPath)

						volStr = '{fr}:{to}'.format(fr=fromPath, to=v['to'])
					else:
						volStr = v['to']

					if 'ro' in v and v['ro'] == True:
						volStr += ':ro'
				else:
					volStr = v
				rc.append(volStr)

		return rc

	def _parseVolumesFrom(self, config):
		rc = None

		if 'volumesFrom' in config:
			rc = config['volumesFrom']
			if type(rc) != list:
				rc = [rc]

			# add containers to dependencies
			for container in rc:
				self.depends[container] = None

		return rc

	@staticmethod
	def _readConfig(name):
		path = None

		if os.path.exists("{0}.rocker".format(name)):
			path = "{0}.rocker".format(name)
		else:
			raise FileNotFoundError("Container contiguration not found: '{0}'".format(name))

		with open(path) as f:
			return json.loads(f.read())

def create(name, docker=DockerClient()):
	config = RockerFile(name)
	# check if the container still uses the most recent image
	if isCurrent(name, config.image):
		print("Not creating '{0}' - nothing changed".format(name))
		return

	# (re)build image if necessary
	if os.path.exists('{0}/Dockerfile'):
		# seems to be a local image => try to (re)build it
		image.build(config.image)

	# check container dependencies (and rebuild them)
	for d in config.depends.keys():
		create(d)

	resp = docker.createClient().doPost('/containers/create?name={0}'.format(name), config.toApiJson())
	if 'Warnings' in resp and resp['Warnings'] != None:
		for w in resp['Warnings']:
			sys.stderr.write("WARNING: {0}\n".format(w))
	if not 'Id' in resp:
		raise Exception("Missing 'Id' in docker response!")

	return resp['Id']

# Returns detailed information about the given image (or None if not found)
def inspect(containerName, docker=DockerClient()):
	rc = None

	with docker.createClient() as c:
		try:
			rc = Container(c.doGet('/containers/{0}/json'.format(containerName)))
		except HttpResponseError as e:
			if e.getCode() == 404:
				pass # return None
			else:
				raise e

	return rc

# checks whether a container uses the current version of the underlying image
def isCurrent(containerName, imageName):
	print('{0} -- {1}'.format(containerName, imageName))
	ctrInfo = inspect(containerName)
	imgInfo = image.inspect(imageName)

	print('{0} -- {1}'.format(ctrInfo, imgInfo))
	if ctrInfo == None:
		# container not found => not using current image
		return False
	elif imgInfo == None:
		# image not found => Error
		raise Exception("Unknown image: {0}", imageName)

	return ctrInfo["Image"] == imgInfo["Id"]
