import rocker
import sys

shortDesc = "\nPrints this information"

# print usage information
# if errorMsg is None, the usage info will be written to stdout and the app will exit with code 0
# If there is an error message, the message will be written to stderr and the program will exit with code 1
def run(args, r, errMsg=None):
	return usage(errMsg)

def usage(errMsg=None):
	out = sys.stdout
	if errMsg != None:
		out = sys.stderr
		out.write("ERROR: {0}\n\n".format(errMsg))

	out.write("USAGE: {0} <command> [arguments]\n\nCOMMANDS:\n".format(sys.argv[0]))

	cmds = list(rocker.listCommands())
	cmds.sort()
	for cmd in cmds:
		mod = rocker.getCommand(cmd)
		desc = mod.shortDesc.replace('\n', '\n\t\t')
		out.write("\t{0} {1}\n".format(cmd, desc))

	out.write("""
OPTIONS:
	-v (can be specified multiple times)
		Increase output verbosity
""".format(sys.argv[0]))
	if errMsg != None:
		sys.exit(1)
