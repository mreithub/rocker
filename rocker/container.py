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
		self.command = Container._getValue(json, 'Command')
		self.created = json['Created']
		self.state = Container._getValue(json, 'State')

	@staticmethod
	def _getValue(data, key, default=None):
		if key in data:
			return data[key]
		else:
			return default

	def isRunning(self):
		rc = False

		if 'Running' in self.state:
			rc = self.state['Running']

		return rc

# Converts .rocker files to the docker API format
class RockerFile:
	def __init__(self, name):
		config = RockerFile._readConfig(name)

		self.depends = {}

		self.name = name
		self.image = RockerFile._getValue(config, 'image', "You need to specify an 'image' for your .rocker container!")

		self.env = RockerFile._getValue(config, 'env')
		self.links = self._parseLinks(config)
		self.ports = RockerFile._parsePorts(config)
		self.raw = RockerFile._getValue(config, 'raw')
		self.volumes = RockerFile._parseVolumes(config, name)
		self.volumesFrom = self._parseVolumesFrom(config)

		self.cmd = RockerFile._getValue(config, 'cmd')
		self.entrypoint = RockerFile._getValue(config, 'entrypoint')

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

		if self.cmd != None:
			rc["Cmd"] = self.cmd

		if self.entrypoint != None:
			rc["Entrypoint"] = self.entrypoint

		hostConfig = {}
		if self.links != None:
			# convert the {'alias': 'containerName', ...} format to ["containerName:alias"]
			links = []
			
			for alias, containerName in self.links.items():
				links.append("{0}:{1}".format(containerName, alias))
			hostConfig['links'] = links

		if self.ports != None:
			portBindings = {}
			for port in self.ports:
				key = "{ext}/{proto}".format(**port)
				extIp = port['extIp']
				if extIp == None:
					extIp = ''

				portBindings[key] = [{"HostIp":extIp, "HostPort": str(port['int'])}]
			hostConfig['PortBindings'] = portBindings

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
					realLinks[v[1]] = v[0]
				rc = realLinks

			elif type(links) == dict: # { alias: containerName, ... }
				rc = links
			else:
				raise ValueError("Unsupported 'links' type: '{0}'".format(type(links)))

			# add links to dependencies (to be able to (re-)build them if necessary)
			for container in rc.values():
				self.depends[container] = None

		return rc

	# expected format is one of:
	# - [ 123, 456, 789, ... ]
	# - [ {proto:tcp, int:123, ext:2123, extIp:...}, ...] <- that's how we store it internally
	@staticmethod
	def _parsePorts(config):
		rc = []

		if 'ports' not in config:
			pass # simply return an empty list
		elif type(config['ports']) != list:
			raise Exception("Expected a port list!")
		else:
			for port in config['ports']:
				if type(port) == int: # format: 123 (simply a number)
					rc.append({'proto': 'tcp', 'int': port, 'ext': port, 'extIp': None})
				elif type(port) == dict: # format: {'int': 123, 'ext': 1234, 'extIp': "127.0.0.1", "proto": "tcp"}
					if not 'int' in port:
						raise Exception("Missing internal port ('int'): {0}".format(port))
					if not 'ext' in port:
						raise Exception("Missing external port ('ext'): {0}".format(port))
					if not 'proto' in port:
						port['proto'] = 'tcp'
					if not 'extIp' in port:
						port['extIp'] = None

					rc.append(port)

			del config['ports']

		return rc

	@staticmethod
	def _parseVolumes(config, containerName):
		rc = None

		if 'volumes' in config:
			rc = []
			for v in config['volumes']:
				volStr = None
				if type(v) == dict: # format: { "from": "path/to/host/dir", "to": "/internal/path", "ro": true }
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

			del config['volumesFrom']

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

	# check if the image is part of the project and if it needs to be built
	if image.existsInProject(config.image):
		image.build(config.image)

	# check container dependencies (and rebuild them)
	for d in config.depends.keys():
		# it seems that for docker links to work properly the containers have to be started at least once.
		# For simplicity, we'll start them now
		run(d)

	# check if the container still uses the most recent image
	if isCurrent(name, config.image, pullImage=True, docker=docker):
		print("Not creating '{0}' - nothing changed".format(name))
		return

	# (re)build image if necessary
	if os.path.exists('{0}/Dockerfile'):
		# seems to be a local image => try to (re)build it
		image.build(config.image)

	# TODO if the container is already running, it should be stopped. But is that always what we want?

	with docker.createRequest().doPost('/containers/create?name={0}'.format(name)) as req:
		resp = req.send(config.toApiJson()).getObject()
		if 'Warnings' in resp and resp['Warnings'] != None:
			for w in resp['Warnings']:
				sys.stderr.write("WARNING: {0}\n".format(w))
		if not 'Id' in resp:
			raise Exception("Missing 'Id' in docker response!")

		return resp['Id']

# Returns detailed information about the given image (or None if not found)
def inspect(containerName, docker=DockerClient()):
	rc = None

	with docker.createRequest() as req:
		try:
			rc = Container(req.doGet('/containers/{0}/json'.format(containerName)).send().getObject())
		except HttpResponseError as e:
			if e.getCode() == 404:
				pass # return None
			else:
				raise e

	return rc

# checks whether a container uses the current version of the underlying image
def isCurrent(containerName, imageName, pullImage=True, docker=DockerClient()):
	ctrInfo = inspect(containerName)
	imgInfo = image.inspect(imageName)

	if imgInfo == None and pullImage == True:
		image.pull(imageName, docker)
		imgInfo = image.inspect(imageName)

	if imgInfo == None:
		raise Exception("Missing image: {0}".format(imageName))

	if ctrInfo == None:
		# container not found => we need to build it
		return False
	elif imgInfo == None:
		# image not found => Error
		raise Exception("Unknown image: {0}", imageName)

	# newer versions of an image will get a new Id
	return ctrInfo.image == imgInfo.id

def run(containerName, docker=DockerClient()):
	create(containerName)

	info = inspect(containerName)
	if info.isRunning():
		print("Not starting {0} - already running".format(containerName))
		return

	config = RockerFile(containerName)

	for d in config.depends:
		run(d)

	with docker.createRequest() as req:
		req.doPost('/containers/{0}/start'.format(containerName)).send()
