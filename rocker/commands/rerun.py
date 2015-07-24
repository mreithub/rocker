from rocker import container
from rocker.commands import help

shortDesc = """<containerName>
Same as run, but instead of failing if a container already exists, it will ask whether to recreate it."""

def run(args, r):
	if len(args) != 2:
		help.usage("'run' expects exactly one argument (the container name)")
	name = args[1]

	#container.run expects a container name as parameter => strip the extension
	if name.endswith('.rocker'):
		name = name[:-7]

	container.run(name, rocker=r, replace=True)