from rocker.container import Container

from unittest import TestCase

class ContainerTest(TestCase):
	# Check that all getters return the value we expect
	# This makes sure all of the fields have been initialized
	def testConstructor(self):
		c = Container()

		self._checkGetters(c, {
			'getDependencies': set(),
			'getEnvironment': {},
			'getLinks': {},
			'getPorts': [],
			'getVolumes': []
		})

	def testMinimalRockerfile(self):
		cfg = { "image": "imgName" }

		newCfg = Container.fromRockerConfig("foo", dict(cfg)).toRockerFile()
		self.assertEqual(cfg, newCfg)

	def testFromToRockerFile(self):
		cfg = {
			"image": "fooImg",
			"env": {
				"VAR1": "value1",
				"VAR2": "value2"
			},
			"links": [
				"mysql:db",
				"container2"
			],
			"ports": [
				80,
				{ "int": 1234, "ext": 2345 }
			],
			"volumes": [
				{ "tgt": "/home" },
				{ "src": "/foo", "tgt": "/bar/"},
				{ "src": "/etc/apt", "tgt": "apt/", "ro": True },
			],
			"volumesFrom": ["other1", "other2"],
			"cmd": ["hello", "world"],
			"entrypoint": ["/bin/echo"],
			"restart": False,
			"raw": {"Foo": 1234}
		}

		try:
			# prevent mkdir calls
			originalMkdirs = Container._mkdirs
			Container._mkdirs = lambda _: None

			newCfg = Container.fromRockerConfig("abc", dict(cfg)).toRockerFile()

			# sort links (we don't care about their order and Container might have reordered them)
			cfg['links'].sort()
			newCfg['links'].sort()

			self.assertEqual(cfg, newCfg)
		finally:
			Container._mkdirs = originalMkdirs

	# Calls all getters and compares their values with those in `expectedValues` (or None if not defined)
	def _checkGetters(self, c: Container, expectedValues: dict):
		for m in dir(c):
			if m.startswith("get"):
				v = getattr(c, m)()
				expected = None

				if m in expectedValues.keys():
					expected = expectedValues[m]

				self.assertEqual(v, expected, "{0} was expected to return {1}, not {2}".format(m, expected, v))
