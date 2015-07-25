#!/usr/bin/python3
#
# Handy tool to simplify docker container management.
#
# try 'rocker help' for usage information.
#

from rocker import commands, restclient
from rocker.commands import help
from rocker.rocker import Rocker

import pkgutil
import sys

_commands = None

def getCommand(name):
	global _commands

	listCommands() # prefetch commands

	if not name in _commands:
		raise Exception("Unknown command: {0}".format(name))

	m = _commands[name].find_module(name).load_module(name)

	# make sure the module contains all the necessary functions+attributes
	for identifier in ['run', 'shortDesc']:
		if not identifier in dir(m):
			raise Exception("Module {0} needs a '{1}' function/attribute".format(name, identifier))

	return m

def listCommands():
	global _commands
	if _commands == None:
		cmds = {}
		for importer, name, isPkg in pkgutil.iter_modules(commands.__path__):
			cmds[name] = importer

		_commands = cmds

	return _commands.keys()

def main():
	rocker = Rocker()

	args = rocker.getopt()

	if rocker.getVerbosity() < 3:
		try:
			return runCommand(args, rocker)
		except restclient.HttpResponseError as e:
			rocker.error("Docker error (code: {0}): {1}".format(e.getCode(), str(e.getData(), "utf8")))
			return 1
		except restclient.SocketError as e:
			rocker.error(e.message)
	else:
		return _debugWrapper(runCommand, args, rocker)


def runCommand(args, rocker):
	if len(args) < 1:
		help.usage("Missing command!")
	cmd = args[0]

	module = getCommand(cmd)
	if module != None:
		module.run(args, rocker)
	else:
		help.usage("Unknown command: '{0}'".format(cmd))

	rocker.printQueuedMessages()

def _debugWrapper(fn, *fnArgs):
	try:
		return fn(*fnArgs)
	except BaseException as e:
		# print local vars (for easier debugging)
		exc_type, exc_value, tb = sys.exc_info()
		if tb is not None:
			prev = tb
			curr = tb.tb_next
			while curr is not None:
				prev = curr
				curr = curr.tb_next
			print("LocalVars: {0}".format(prev.tb_frame.f_locals))

		# reraise exception
		raise e