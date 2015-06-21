rocker - Docker container management
====================================

rocker simplifies managing docker containers.

With plain Docker, you have to specify instance-specific options as commandline arguments.
rocker uses simple JSON files (so called `.rocker` files) to do that.

On top of that, it will automatically rebuild/recreate any images/containers the current one depends on (if they changed).
