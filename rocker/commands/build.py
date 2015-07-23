from rocker import image
from rocker.commands import help

shortDesc = """<image path>
Builds the docker image in the specified subdir"""

def run(args, r):
	if len(args) != 2:
		help.usage(None, "'build' expects exactly one argument (the image path)")
		image.build(args[1], rocker=r)
