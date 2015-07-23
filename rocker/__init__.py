#!/usr/bin/python3
#
# Handy tool to simplify docker container management.
#
# try 'rocker help' for usage information.
#

from rocker import container, restclient
from rocker.rocker import Rocker

import sys

# print usage information
# if errorMsg is None, the usage info will be written to stdout and the app will exit with code 0
# If there is an error message, the message will be written to stderr and the program will exit with code 1
def usage(errMsg=None):
	out = sys.stdout
	if errMsg != None:
		out = sys.stderr
		out.write("ERROR: {0}\n\n".format(errMsg))

	out.write("""USAGE: {0} <command> [arguments]

COMMANDS:
	help
		Prints this information
	build <image path>
		Builds the docker image in the specified subdir
	run <container.rocker>
		Creates and starts the specified container. Will build/create underlying images/containers first.
		Will skip any container/image that hasn't been changed.
	version
		Prints version information for rocker and the Docker daemon
		(try -v or -vv to increase detail)

OPTIONS:
	-v (can be specified multiple times)
		Increase output verbosity
""".format(sys.argv[0]))
	if errMsg != None:
		sys.exit(1)

def main():
	rocker = Rocker()

	args = rocker.getopt()

	if rocker.getVerbosity() < 3:
		try:
			return run(args, rocker)
		except restclient.HttpResponseError as e:
			rocker.printDockerMessage({'error': "Docker error (code: {0}): {1}".format(e.getCode(), str(e.getData(), "utf8"))})
			return 1
	else:
		return _debugWrapper(run, args, rocker)


def run(args, rocker):
	if len(args) < 1:
		usage("Missing command!")
	cmd = args[0]

	if cmd == 'help':
		usage()
	elif cmd == 'build':
		if len(args) != 2:
			usage("'build' expects exactly one argument (the image path)")
		image.build(args[1], rocker=rocker)
	elif cmd == 'run':
		if len(args) != 2:
			usage("'run' expects exactly one argument (the container name)")
		name = args[1]

		#container.run expects a container name as parameter => strip the extension
		if name.endswith('.rocker'):
			name = name[:-7]

		container.run(name, rocker=rocker)
	elif cmd == 'version':
		rocker.printVersion()
	else:
		usage("Unknown command: '{0}'".format(cmd))

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