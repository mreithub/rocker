from rocker import container
from rocker.commands import help

shortDesc = """<container.rocker>
Creates and starts the specified container. Will build underlying images first.
Will skip any container/image that hasn't been changed."""

def run(args, r):
	if len(args) != 2:
		help.usage("'run' expects exactly one argument (the container name)")
	name = args[1]

	#container.run expects a container name as parameter => strip the extension
	if name.endswith('.rocker'):
		name = name[:-7]

	container.run(name, r=r)
