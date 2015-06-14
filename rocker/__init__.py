#!/usr/bin/python3
#
# Handy tool to simplify docker container management.
#
# try 'rocker help' for usage information.
#

from rocker import container

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
	help
		Prints this information
	build <image path>
		Builds the docker image in the specified subdir
	create <container.rocker>
		Creates a container as specified in the .rocker file.
		Also will build dependent containers and the underlying images
		if they have changed.
	run <container.rocker>
		Runs the specified container. Will issue build and create first 
""".format(sys.argv[0]))
	if errMsg != None:
		sys.exit(1)

def main():
	if len(sys.argv) <= 1:
		usage("Missing command!")
	cmd = sys.argv[1]

	if cmd == 'help':
		usage()
	elif cmd == 'build':
		if len(sys.argv) != 3:
			usage("'build' expects exactly one argument (the image path)")
		image.build(sys.argv[2])
	elif cmd == 'create':
		if len(sys.argv) != 3:
			usage("'create' expects exactly one argument (the .rocker file)")

		name = sys.argv[2]

		#container.create expects a container name as parameter => strip the extension
		if name.endswith('.rocker'):
			name = name[:-7]

		container.create(name)
	else:
		usage("Unknown command: '{0}'".format(cmd))