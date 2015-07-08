from rocker import image
from rocker.rocker import Rocker
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
	class Volume:
		def __init__(self, tgt, src=None, ro=False):
			self.src = src
			self.tgt = tgt
			self.ro = ro

	def __init__(self, name):
		config = RockerFile._readConfig(name)

		self.depends = {}

		self.name = name
		self.image = RockerFile._getValue(config, 'image', "You need to specify an 'image' for your .rocker container!")

		self.env = RockerFile._getValue(config, 'env')
		self.links = self._parseLinks(config)
		self.ports = RockerFile._parsePorts(config)
		self.raw = RockerFile._getValue(config, 'raw')
		self.restart = RockerFile._getValue(config, 'restart', defaultValue=True)
		self.volumes = RockerFile._parseVolumes(config, name)
		self.volumesFrom = self._parseVolumesFrom(config)

		self.cmd = RockerFile._getValue(config, 'cmd')
		self.entrypoint = RockerFile._getValue(config, 'entrypoint')

		# all the remaining keys in data are unsupporyed => issue warnings
		for key in config.keys():
			sys.stderr.write("WARNING: unsupported .rocker key: '{0}'\n".format(key))

	def toApiJson(self):
		rc = {}
		hostConfig = {}

		# non-raw entries override raw ones => seed from raw first
		if self.raw != None:
			rc = self.raw;

		# image
		rc['Image'] = self.image

		# env
		if self.env != None:
			env = []
			for key, value in self.env.items():
				env.append("{0}={1}".format(key, value))
			rc['Env'] = env

		# cmd
		if self.cmd != None:
			rc["Cmd"] = self.cmd

		# entrypoint
		if self.entrypoint != None:
			rc["Entrypoint"] = self.entrypoint

		# restart policy
		if self.restart in [True, "always"]:
			rc["RestartPolicy"] = "always"
		elif self.restart == "on-failure":
			rc["RestartPolicy"] = "on-failure"
		elif type(self.restart) == int:
			rc["RestartPolicy"] = "on-failure"
			rc["MaximumRetryCount"] = self.restart
		elif self.restart == False:
			#rc["RestartPolicy"] = <undefined>
			pass
		else:
			raise ValueError("invalid 'restart' policy value in {0}: '{1}'".format(self.name, self.restart))

		# links
		if self.links != None:
			# convert the {'alias': 'containerName', ...} format to ["containerName:alias"]
			links = []
			
			for alias, containerName in self.links.items():
				links.append("{0}:{1}".format(containerName, alias))
			hostConfig['links'] = links

		# ports
		if self.ports != None:
			portBindings = {}
			for port in self.ports:
				key = "{int}/{proto}".format(**port)
				extIp = port['extIp']
				if extIp == None:
					extIp = ''

				portBindings[key] = [{"HostIp":extIp, "HostPort": str(port['ext'])}]
			hostConfig['PortBindings'] = portBindings

		# volumes
		if self.volumes != None:
			volumeList = {}
			bindList = []
			for volume in self.volumes:
				# docker distinguishes between host volumes (aka 'binds') and internal volumes
				if volume.src != None:
					# bind mount
					if volume.ro:
						bindStr = "{0}:{1}:ro"
					else:
						bindStr = "{0}:{1}"
					bindList.append(bindStr.format(volume.src, volume.tgt))
				else:
					# internal volume
					volumeList[volume.tgt] = {}

			if len(volumeList) > 0:
				rc['Volumes'] = volumeList
			if len(bindList) > 0:
				hostConfig['Binds'] = bindList

		rc['HostConfig'] = hostConfig

		return rc

	@staticmethod
	def _getValue(data, key, errMsg=None, defaultValue=None):
		rc = defaultValue
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

	# returns a list of Volume objects (with .src, .tgt and .ro properties)
	@staticmethod
	def _parseVolumes(config, containerName):
		rc = None

		if 'volumes' in config:
			rc = []
			for v in config['volumes']:
				src = None
				tgt = None
				ro = False

				if type(v) == dict: # format: { "src": "path/to/host/dir", "tgt": "/internal/path", "ro": true }
					if not 'tgt' in v:
						raise ValueError("Volume config needs a 'tgt' field!")
					tgt = v['tgt']

					if 'src' in v:
						# create host directory if necessary
						srcPath = os.path.join('/docker', containerName, v['src'])
						RockerFile._mkdirs(srcPath)
						src = srcPath

					if 'ro' in v and v['ro'] == True:
						ro = True

				else: # format: "/internal/path"
					tgt = v

				rc.append(RockerFile.Volume(tgt, src, ro))
			del config['volumes']

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

def create(name, rocker=Rocker()):
	config = RockerFile(name)

	# check if the image is part of the project and if it needs to be built
	if image.existsInProject(config.image):
		image.build(config.image, rocker)

	# check container dependencies (and rebuild them)
	for d in config.depends.keys():
		# it seems that for docker links to work properly the containers have to be started at least once.
		# For simplicity, we'll start them now
		run(d, rocker)

	# check if the container still uses the most recent image
	if isCurrent(name, config.image, pullImage=True, rocker=rocker):
		rocker.debug(1, "Not creating '{0}' - nothing changed".format(name), duplicateId=(name,'create'))
		return

	rocker.info("Creating container: {0}".format(name), duplicateId=(name,'create'))

	# (re)build image if necessary
	if os.path.exists('{0}/Dockerfile'):
		# seems to be a local image => try to (re)build it
		image.build(config.image, rocker)

	# TODO if the container is already running, it should be stopped. But is that always what we want?

	with rocker.createRequest().doPost('/containers/create?name={0}'.format(name)) as req:
		resp = req.send(config.toApiJson()).getObject()
		if 'Warnings' in resp and resp['Warnings'] != None:
			for w in resp['Warnings']:
				sys.stderr.write("WARNING: {0}\n".format(w))
		if not 'Id' in resp:
			raise Exception("Missing 'Id' in docker response!")

		return resp['Id']

# Returns detailed information about the given image (or None if not found)
def inspect(containerName, rocker=Rocker()):
	rc = None

	with rocker.createRequest() as req:
		try:
			rc = Container(req.doGet('/containers/{0}/json'.format(containerName)).send().getObject())
		except HttpResponseError as e:
			if e.getCode() == 404:
				pass # return None
			else:
				raise e

	return rc

# checks whether a container uses the current version of the underlying image
def isCurrent(containerName, imageName, pullImage=True, rocker=Rocker()):
	ctrInfo = inspect(containerName)
	imgInfo = image.inspect(imageName)

	if imgInfo == None and pullImage == True:
		image.pull(imageName, rocker)
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

def run(containerName, rocker=Rocker()):
	create(containerName, rocker)

	info = inspect(containerName)
	if info.isRunning():
		rocker.debug(1, "Not starting {0} - already running".format(containerName), duplicateId=(containerName,'run'))
		return

	rocker.info("Starting container: {0}".format(containerName), duplicateId=(containerName,'run'))

	config = RockerFile(containerName)

	for d in config.depends:
		run(d, rocker)

	with rocker.createRequest() as req:
		req.doPost('/containers/{0}/start'.format(containerName)).send()
