from rocker import image, rocker
from rocker.restclient import HttpResponseError

import hashlib
import json
import os
import sys

# data class representing a Docker container
class Container:
	class Port:
		def __init__(self, data):
			if type(data) == int: # format: 123 (simply a number)
				self.proto = 'tcp'
				self.int = data
				self.ext = data
				self.extIp = None
			elif type(data) == dict: # format: {'int': 123, 'ext': 1234, 'extIp': "127.0.0.1", "proto": "tcp"}
				if not 'int' in data:
					raise Exception("Missing internal port ('int'): {0}".format(data))
				if not 'ext' in data:
					raise Exception("Missing external port ('ext'): {0}".format(data))
				self.int = data['int']
				self.ext = data['ext']

				self.proto = Container._getValue(data, 'proto', defaultValue='tcp')
				self.extIp = Container._getValue(data, 'extIp')

		def toRockerFormat(self):
			rc = {}

			if self.int == self.ext and self.proto in [None, 'tcp'] and self.extIp == None:
				rc = self.int
			else:
				Container._putValue(rc, 'int', self.int)
				Container._putValue(rc, 'ext', self.ext)
				Container._putValue(rc, 'proto', self.proto)
				Container._putValue(rc, 'extIp', self.extIp)
			return rc

	class Volume:
		def __init__(self, tgt, src=None, ro=False):
			self.src = src
			self.tgt = tgt
			self.ro = ro

		def toRockerFormat(self):
			rc = {'tgt': self.tgt}

			if self.src != None:
				rc['src'] = self.src
			if self.ro != False:
				rc['ro'] = self.ro
			return rc

	def __init__(self, r=rocker.Rocker()):
		self._id = None
		self._name = None
		self._image = None

		self._created = None
		self._caps = []
		self._env = {}
		self._hosts = {}
		self._labels = {}
		self._links = {}
		self._netMode = None
		self._ports = []
		self._privileged = None
		self._raw = None
		self._restart = None
		self._state = None
		self._volumes = []
		self._volumesFrom = None

		self._cmd = None
		self._entrypoint = None

		self._depends = set()

		self._rocker = r

	def getId(self):
		return self._id

	def getHosts(self):
		return self._hosts

	def getImage(self):
		return self._image

	def getName(self):
		return self._name

	def getCapabilities(self):
		return self._caps

	def getCreatedAt(self):
		return self._created

	def getEnvironment(self):
		return self._env

	def getLabels(self):
		return self._labels

	def getLinks(self):
		return self._links

	def getNetworkMode(self):
		return self._netMode

	def getPorts(self):
		return self._ports

	def getPrivileged(self):
		return self._privileged

	def getRawData(self):
		return self._raw

	def getRestartPolicy(self):
		return self._restart

	def getState(self):
		return self._state

	def getVolumes(self):
		return self._volumes

	def getVolumesFrom(self):
		return self._volumesFrom


	def getDependencies(self):
		return self._depends

	# Create a Container object from Docker's remote API format
	@staticmethod
	def fromApiJson(json, r=rocker.Rocker()):
		json = dict(json) # copy data (as _getValue() will mutate its contents)
		rc = Container(r)
		rc._id = json['Id']
		rc._name = Container._getValue(json, 'Name')
		rc._image = json['Image']

		rc._created = json['Created'] # TODO parse date
		rc._state = Container._getValue(json, 'State') # TODO parse value map

		if 'Config' in json:
			config = json['Config']
			if 'Env' in config and type(config['Env']) == list:
				# environment variables
				rc._env = {}
				for e in config['Env']:
					var, value = e.split('=', 1)
					rc._env[var] = value

		if 'HostConfig' in json:
			hostConfig = json['HostConfig']
			rc._netMode = Container._getValue(hostConfig, 'NetworkMode')

			if 'CapAdd' in hostConfig and type(hostConfig['CapAdd']) == list:
				for c in hostConfig['CapAdd']:
					rc._caps.append(c)
			if 'CapDrop' in hostConfig and type(hostConfig['CapDrop']) == list:
				for c in hostConfig['CapDrop']:
					rc._caps.append('-{0}'.format(c))
			if 'ExtraHosts' in hostConfig and type(hostConfig['ExtraHosts']) == list:
				hosts = {}
				for h in hostConfig['ExtraHosts']:
					h = h.split(':')
					if len(h) != 2:
						raise ValueError("ExtraHosts entry expected to have exactly one colon: {0}".format(hostConfig['ExtraHosts']))
					hosts[h[0]] = h[1]
				rc._hosts = hosts
			if 'Privileged' in hostConfig:
				rc._privileged = hostConfig['Privileged'] == True

		# TODO parse links
		# TODO parse ports
		# TODO parse restart policy
		# TODO parse volumes
		# TODO parse volumesFrom

		# TODO init dependencies

		rc._cmd = Container._getValue(json, 'Cmd')
		rc._entrypoint = Container._getValue(json, 'Entrypoint')

		return rc

	@staticmethod
	def fromRockerFile(name, r=rocker.Rocker()):
		config = Container._readConfig(name, r)
		return Container.fromRockerConfig(name, config, r)

	@staticmethod
	def fromRockerConfig(name, config, r=rocker.Rocker()):
		rc = Container(r)

		rc._name = name
		rc._image = Container._getValue(config, 'image', "You need to specify an 'image' for your .rocker container!")

		rc._caps = Container._getValue(config, 'caps')
		rc._env = Container._getValue(config, 'env')
		rc._hosts = Container._getValue(config, 'hosts')
		rc._labels = Container._getValue(config, 'labels', defaultValue={})
		rc._links = rc._parseLinks(config)
		rc._netMode = Container._getValue(config, 'netMode')
		rc._ports = Container._parsePorts(config)
		rc._privileged = Container._getValue(config, 'privileged', defaultValue=False)
		rc._raw = Container._getValue(config, 'raw')
		rc._restart = Container._getValue(config, 'restart', defaultValue=True)
		rc._volumes = Container._parseVolumes(config, name)
		rc._volumesFrom = rc._parseVolumesFrom(config)

		rc._cmd = Container._getValue(config, 'cmd')
		rc._entrypoint = Container._getValue(config, 'entrypoint')

		# all the remaining keys in data are unsupporyed => issue warnings
		for key in config.keys():
			sys.stderr.write("WARNING: unsupported .rocker key: '{0}'\n".format(key))

		return rc

	def isRunning(self):
		rc = False

		if 'Running' in self._state:
			rc = self._state['Running']

		return rc

	def toApiJson(self):
		rc = {}
		hostConfig = {}

		# non-raw entries override raw ones => seed from raw first
		if self._raw != None:
			rc = self._raw;
			if 'HostConfig' in rc:
				hostConfig = rc['HostConfig'] # make sure to also preseed the hostConfig variable

		Container._putValue(rc, "Image", self._image)
		Container._putValue(rc, "Cmd", self._cmd)
		Container._putValue(rc, "Entrypoint", self._entrypoint)

		# caps
		if self._caps != None and len(self._caps) > 0:
			capAdd = []
			capDrop = []

			for c in self._caps:
				if not c.startswith('-'):
					capAdd.append(c)
				else:
					capDrop.append(c[1:])

			hostConfig['CapAdd'] = capAdd
			hostConfig['CapDrop'] = capDrop

		# env
		if self._env != None:
			env = []
			for key, value in self._env.items():
				env.append("{0}={1}".format(key, value))
			rc['Env'] = env

		# extra hosts
		if self._hosts != None and len(self._hosts) > 0:
			hosts = []
			for host, ip in self._hosts.items():
				hosts.append('{0}:{1}'.format(host, ip))
			hostConfig['ExtraHosts'] = hosts

		# Labels
		if self._labels != None and len(self._labels) > 0:
			Container._putValue(rc, "Labels", self._labels)

			if not self._rocker.checkApiVersion(rocker.MIN_LABELS_VERSION):
				self._rocker.warning("WARNING: You're using labels in container {0}, but your Docker doesn't support them (upgrade to at least v1.6)".format(self._name), duplicateId="noLabels")

		# links
		if self._links != None:
			# convert the {'alias': 'containerName', ...} format to ["containerName:alias"]
			links = []
			
			for alias, containerName in self._links.items():
				links.append("{0}:{1}".format(containerName, alias))
			hostConfig['links'] = links

		# ports
		if self._ports != None:
			portBindings = {}
			for port in self._ports:
				key = "{int}/{proto}".format(int=port.int, proto=port.proto)
				extIp = port.extIp
				if extIp == None:
					extIp = ''

				portBindings[key] = [{"HostIp":extIp, "HostPort": str(port.ext)}]
			hostConfig['PortBindings'] = portBindings

		# privileged mode
		if self._privileged == True:
			hostConfig['Privileged'] = True

		# volumes
		if self._volumes != None:
			volumeList = {}
			bindList = []
			for volume in self._volumes:
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

		# restart policy
		restartPolicy = {}
		if self._restart in [True, "always"]:
			restartPolicy["Name"] = "always"
		elif self._restart == "on-failure":
			restartPolicy["Name"] = "on-failure"
		elif type(self._restart) == int:
			restartPolicy = {"Name": "on-failure", "MaximumRetryCount": self._restart}
		elif self._restart == False:
			restartPolicy = None
			pass
		else:
			raise ValueError("invalid 'restart' policy value in {0}: '{1}'".format(self._name, self._restart))

		Container._putValue(hostConfig, "RestartPolicy", restartPolicy)


		Container._putValue(hostConfig, "NetworkMode", self._netMode)

		rc['HostConfig'] = hostConfig

		return rc

	# Creates a rocker file from the information stored inside the Container object.
	# If outFile is None, this method will simply return a dict() object which can then be converted to JSON
	# You can specify outFile as file-like object or as path string
	#
	# Keep in mind that this method doesn't resolve image IDs to image names and might contain information that's been
	# automatically generated (i.e. environment variables).
	#
	# So while it's possible to create .rocker files out of existing containers, you shouldn't rely on them being perfect.
	def toRockerFile(self, outFile=None):
		data = {}

		data['image'] = self._image

		Container._putValue(data, 'raw', self._raw)

		Container._putValue(data, 'env', self._env)
		Container._putValue(data, 'cmd', self._cmd)
		Container._putValue(data, 'entrypoint', self._entrypoint)
		Container._putValue(data, 'netMode', self._netMode)
		Container._putValue(data, 'hosts', self._hosts)

		if self._restart not in [True, 'always']: 
			Container._putValue(data, 'restart', self._restart)

		# links
		links = []
		for alias, ctrName in self._links.items():
			if alias == ctrName:
				links.append(ctrName)
			else:
				links.append("{0}:{1}".format(ctrName, alias))
		Container._putValue(data, 'links', links)

		# ports
		ports = []
		for p in self._ports:
			ports.append(p.toRockerFormat())
		Container._putValue(data, 'ports', ports)

		# volumes
		volumes = []
		for v in self._volumes:
			volumes.append(v.toRockerFormat())

		Container._putValue(data, 'volumes', volumes)
		Container._putValue(data, 'volumesFrom', self._volumesFrom)

		if outFile == None:
			return data
		elif type(outFile) == str:
			with open(outFile, 'w') as f:
				json.dump(data, outFile)
		else:
			json.dump(data, outFile)

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

	# Parse links in a .rocker file
	def _parseLinks(self, config):
		rc = {}

		if 'links' in config:
			# we want links to be in the format {"alias": "containerName", ...}
			links = Container._getValue(config, 'links')
			if type(links) == list: # [ "container1", "container2:alias", ... ]
				# parse each item and add them to the list
				realLinks = {}
				for v in links:
					v = v.split(':', maxsplit=1)
					if len(v) == 1:
						v.append(v[0]) # alias=containerName
					realLinks[v[1]] = v[0]
				rc = realLinks

			elif type(links) == dict: # { alias: containerName, ... }
				rc = links
			else:
				raise ValueError("Unsupported 'links' type: '{0}'".format(type(links)))

			# add links to dependencies (to be able to (re-)build them if necessary)
			for container in rc.values():
				self._depends.add(container)

		return rc

	# Parse ports specified in a .rocker file
	# expected format is one of:
	# - [ 123, 456, 789, ... ]
	# - [ {proto:tcp, int:123, ext:2123, extIp:...}, ...] <- that's how we store them internally
	@staticmethod
	def _parsePorts(config):
		rc = []

		if 'ports' not in config:
			pass # simply return an empty list
		elif type(config['ports']) != list:
			raise Exception("Expected a port list!")
		else:
			for port in config['ports']:
				rc.append(Container.Port(port))

			del config['ports']

		return rc

	# returns a list of Volume objects (with .src, .tgt and .ro properties)
	@staticmethod
	def _parseVolumes(config, containerName):
		rc = []

		if 'volumes' in config:
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
						if not os.path.exists(srcPath): # TODO this won't work if docker's running on a remote host
							Container._mkdirs(srcPath)
						src = srcPath

					if 'ro' in v and v['ro'] == True:
						ro = True

				else: # format: "/internal/path"
					tgt = v

				rc.append(Container.Volume(tgt, src, ro))
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
				self._depends.add(container)

			del config['volumesFrom']

		return rc

	def _putValue(data, key, value):
		if value not in [None, [], {}]:
			data[key] = value

	@staticmethod
	def _readConfig(name, r=rocker.Rocker()):
		path = None

		if os.path.exists("{0}.rocker".format(name)):
			path = "{0}.rocker".format(name)
		else:
			raise FileNotFoundError("Container configuration not found: '{0}'".format(name))

		with open(path) as f:
			rc = json.loads(f.read())

			if r.checkApiVersion(rocker.MIN_LABELS_VERSION):
				# add the file's sha256 hash to the container's labels
				# note that we're parsing+dumping the JSON file to assure getting the same hash regardless of whitespaces
				# This label also serves as a check whether or not a container has been created by rocker
				# (Docker supports container labels since v1.6 (API v1.17) so rocker will issue a warning if labels are used but not supported)
				chksum = hashlib.sha256(json.dumps(rc, sort_keys=True).encode('utf8')).hexdigest()
				if not 'labels' in rc:
					rc['labels'] = {}
				rc['labels']['zone.coding.rocker.fileHash'] = chksum

			return rc

# Returns detailed information about the given image (or None if not found)
def inspect(containerName, r=rocker.Rocker()):
	rc = None

	with r.createRequest() as req:
		try:
			rc = Container.fromApiJson(req.doGet('/containers/{0}/json'.format(containerName)).send().getObject(), r=r)
		except HttpResponseError as e:
			if e.getCode() == 404:
				pass # return None
			else:
				raise e

	return rc

# checks whether a container uses the current version of the underlying image
def isCurrent(containerName, imageName, pullImage=True, r=rocker.Rocker()):
	ctrInfo = inspect(containerName)
	imgInfo = image.inspect(imageName)

	if imgInfo == None and pullImage == True:
		image.pull(imageName, r)
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
	return ctrInfo.getImage() == imgInfo.id

def run(containerName, r=rocker.Rocker(), replace=False):
	config = Container.fromRockerFile(containerName, r=r)
	rc = False

	# check if the image is part of the project and if it needs to be built
	if image.existsInProject(config.getImage()):
		if image.build(config.getImage(), r):
			# image was (re)built -> create container
			rc = True

	# check container dependencies (and rebuild them)
	for d in config.getDependencies():
		# it seems that for docker links to work properly the containers have to be started at least once.
		# Just creating them isn't sufficient
		if run(d, r):
			# at least one of the dependencies was started => create container
			rc = True

	# check if the container still uses the most recent image
	if not isCurrent(containerName, config.getImage(), pullImage=True, r=r):
		rc = True

	if rc:
		r.info("Deploying container: {0}".format(containerName))
		_create(containerName, config, r, replace)
		_run(containerName, r)
	else:
		r.info("Skipping container {0} - nothing changed".format(containerName), duplicateId=(containerName,'create'))

	return rc

def _create(containerName, config, r, replace):
	try:
		with r.createRequest().doPost('/containers/create?name={0}'.format(containerName)) as req:
			resp = req.send(config.toApiJson()).getObject()
			if 'Warnings' in resp and resp['Warnings'] != None:
				for w in resp['Warnings']:
					sys.stderr.write("WARNING: {0}\n".format(w))
			if not 'Id' in resp:
				raise Exception("Missing 'Id' in docker response!")
	except HttpResponseError as e:
		if e.getCode() == 409:
			# Conflict -> fail
			if replace:
				choice = r.choice("Do you want to replace container '{0}'? You will lose non-persistent data!".format(containerName), default='n')
				if choice == 'y':
					# issue a delete call
					with r.createRequest().doDelete('/containers/{0}?force=1'.format(containerName)) as req:
						req.send()

					# recursively call myself
					_create(containerName, config, r, replace)
				else:
					r.error("ERROR: Refused to overwrite container: {0}".format(containerName))
			else:
				r.error("ERROR: Container exists but is not up to date: {0}".format(containerName))

				r.info("""
Some containers need to be replaced, but `rocker run` won't do that (to avoid deleting data accidentally).
If you want to replace the container, have a look at `rocker rerun`""", stream=sys.stderr, duplicateId="rerunMsg", delayed=True)
		else:
			raise e

def _run(containerName, r):
	info = inspect(containerName)
	if not info.isRunning():
		r.info("Starting container: {0}".format(containerName), duplicateId=(containerName,'run'))

		with r.createRequest() as req:
			req.doPost('/containers/{0}/start'.format(containerName)).send()
	else:
		r.debug(1, "Not starting {0} - already running".format(containerName), duplicateId=(containerName,'run'))
