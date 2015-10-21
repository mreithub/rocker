rocker - Docker build tool
==========================

rocker aims to ease the creation and deployment of Docker images/containers.

It uses so called ``.rocker`` files, rather simple JSON files which serve as a counterpart to Dockerfiles but for containers.

``rocker`` is meant to be a useful extension to Docker, not a replacement.

There are three main commands:

- ``rocker build <dir>`` builds the specified image (and sets its name to the value of ``<dir>``).

  But before it does so, it also parses the Dockerfile's ``FROM`` line and (if the parent image is part of the project - i.e. ``parentImage/Dockerfile`` exists) try to build that one as well.

  It will only build images if things have changed though (it maintains a file called ``.dockerBuild`` to do so).
- ``rocker create <containerName>`` creates a container using the ``.rocker`` file specified by ``<containerName>``. It's up to you whether or not you want to omit the file extension.

  Before it creates the container in question, it tries to (re)create containers this one depends on (those specified in ``links``, ``volumes`` or ``volumesFrom``) and (re)build the underlying image.

  The container will only be recreated if necessary (i.e. it doesn't exist yet or the underlying image was updated since the container was last created)
- ``rocker run <containerName>`` runs the specified container (after issuing ``create``) if it wasn't started already.
- ``rocker help`` shows a short usage message.

Right now rocker will fail if you attempt to overwrite containers. This is intentional. If you want to recreate containers, make sure you stop and delete them first (``docker stop``/``docker kill`` and ``docker rm``).

There are however plans to implement either a ``--force``, a ``cleanup`` command or something like that.

Installation
------------

rocker can be installed via pypi_ simply by issuing

.. code::

    pip install rocker

If you want to contribute, clone the GitHub_ repository.

``.rocker`` files
-----------------

The ``examples/`` directory of the GitHub_ repository contains a few example projects you might want to take a look at.

rocker files are simple JSON files. Let's start with a minimal rocker file (let's call it ``myApp.rocker``):

.. code:: json

    {
        "image": "acme/app"
    }

Running ``rocker create myApp`` rebuilds the image (if necessary - and if it's part of the project) and then creates the container (and names it ``myApp`` using the file name as reference).

The following is a complete example of all supported configuration options:

.. code:: json

    {
        "image": "acme/app",
		"caps": [
			"ALL",
			"-MKNOD"
		]
        "env": {
            "ADMIN_PASSWORD": "hackme"
        },
        "hosts": {
            "dnsserver": "8.8.8.8"
        },
        "links": [
            "postgres:db", "mail"
        ],
        "ports": [
            1234,
            { "int": "80", "ext": "8000" },
            ...
        ],
        "volumes": [
            { "tgt": "/data" },
            { "src": "psql", "tgt": "/var/lib/postgresql/data/" },
            { "src": "/home/user/app", "tgt": "/app", "ro": true },
            ...
        ],
        "cmd": ["echo", "hello world"],
        "entrypoint": ["echo", "foo"],
        "netMode": "bridge",
        "privileged": false,
        "restart": true,
        "volumesFrom": ["app-data"],
        "raw": {...}
    }

Description:

- ``"image": "acme/app"``

  Specifies the underlying image of the container. If the image exists in the project directory
  (i.e. ``acme/app/Dockerfile`` exists), a ``rocker build`` will be issued for the image.

  It is up to you if you want to use qualified image names (in the format ``user/image``).
  If you do, make sure you have a your directory structure set up accordingly.
  
  Note: Docker expects image names to follow the following format: ``[a-z0-9-_.]+``

- ``"caps": ["ALL", "-MKNOD"]``

  Adds/drops container capabilities. If you want to drop caps, prepend the string with a dash (``-``).

  There's the special value ``ALL`` that will add all capabilities to the container.
  So the above example allows the container to do pretty much anything but invoke ``mknod`` calls.
  Keep in mind though that there are good reasons for being restrictive about capabilities
  (processes running in a container with ``ALL`` caps can easily break out of them and therefore compromise
  other containers as well as the host itself).

  For a list of supported capabilities have a look at `docker run docs`_' or `capabilities manpage`_

- ``"env": {...}``

  Sets environment variables inside the container.

  ``env`` expects a JSON string map with variable names and their values

- ``"hosts": {"hostname": "ip", ...}``

  Allows you to specify host/ip tuples to be added to the container's ``/etc/hosts`` file.
  Docker takes control of that file so any changes you make to it directly will most likely be lost at some point.
  To be able to add your own entries anyway you can use this setting (which is equivalent to ``docker run``'s ``--add-host`` option).

- ``"links": ["otherContainer", "thirdContainer:alias", ...]``

  Adds a link to another container (i.e. an entry in the container's ``/etc/hosts`` file (and some environment variables - for details see the Docker docs).

  This will also add the linked containers to this container's dependencies (and therefore attempt to recreate them if necessary).
- ``"ports": [1234, 567, ...]``

  Sets up port forwarding for the specified ports.
  You can specify each port in one of the following formats:

  - ``123`` (numeric)

    Tells Docker to listen at port 123 and forward requests to the container's port 123
    (equivalent to Docker's ``-p 123:123`` flag)

    Shorthand for ``{"int": 123, "ext": 123}``

  - ``{'int': 123, 'ext': 1234, 'extIp': "127.0.0.1", "proto": "tcp"}``

    Forwards the host's port 1234 to the container's port 123 (but only listen at the ``lo`` interface - and only forwards TCP connections)

    The parameters ``int`` and ``ext`` are mandatory. ``proto`` default to ``tcp`` and ``ip`` to ``null`` (i.e. all interfaces)

    ``proto`` can be ``tcp`` or ``udp``.
- ``"volumes": [{"src": "host/path/", "tgt": "/container/path", "ro": true}, ...]``

  Specifies a volume for the container.

  - ``tgt`` is mandatory and specifies the *absolute* path of the volume inside the container.
  - ``src`` is optional. If you specify it, Docker will mount a host directory as container volume.

    If the path is relative (i.e. doesn't start with a ``/``), rocker will rewrite it to
    ``/docker/{containerName}/{relPath}`` and create that directory if necessary.
    It defaults to ``null``.

  - ``ro`` can be specified for host based volumes (in conjunction with ``src``) and allows you
    to mount host directories in read only mode. It defaults to ``false``.
- ``"volumesFrom": ["otherContainer", ...]``

  Mount volumes from another container (see the Docker docs about `data volume container`_).

  Can be specified as simple string or as list (i.e. ``"foo"`` is equivalent to ``["foo"]``.
  You can't use that shorthand if you want to use more than one container's volumes).

  rocker will add each of these containers to the container's dependency list
  (and will therefore attempt to (re)create those before creating this one).
- ``"cmd": ["/path/to/command", "arg1", "arg2", ...]``

  Specify the command to run when starting the container.

  Expects a list of strings, one argument per item. The first item is the command's name/path
  (will use the container's ``$PATH`` to find commands)

- ``"entrypoint": ["/path/to/command", "arg1", "arg2", ...]``

  Similar to ``"cmd": [...]``.

- ``"netMode": "bridge"``

  Set the container's network mode. The string value you set here will be sent to Docker unmodified.

  Supported values (at the time of writing):

  - ``bridge`` (default): The container will get its own internal IP on Docker's virtual network interface (default: ``docker0``)
  - ``host``: The container shares the host's network interfaces (and therefore can dynamically bind any unused port on the host).
  - ``container:<name|id>``: Share another container's interface(s).

- ``"privileged": false``

  When set to true, the docker container will run in the so called *privileged* mode.

  Containers running in the privileged mode may pose a serious security risk, so you should only use it if you know what you're doing (In most cases it's better to use ``"caps"`` instead).

  Have a look at the `docker run docs`_' for details.

- ``"restart": true``

  Set the restart policy of the container.

  Supported values:

  - ``true``/``"always"`` (default): Tell docker to always restart the container if it exited/crashed as well as when the system boots
  - ``on-failure``: Only restart the container if it exited with a nonzero exit code.
  - ``false``: Don't restart the container

- ``"raw": {...}``

  Special configuration value to use Docker features that haven't yet been implemented in rocker.

  The configuration specified inside ``raw`` will be sent to Docker without modification.
  Read Docker's `Remote API`_ for information on what to put in here.

  Keep in mind that any other values set directly (all the above) will overwrite values you specify inside ``raw``.

Example projects
----------------

The following list of example projects is (roughly) sorted by complexity, so if you're looking for a quick way to 

Each example contains a README.md describing the details on what's going on.

- postgres_: Simple Database container project. There's one container for the database process and one as `data volume container`_. No custom images.
- wordpress_: This project creates a MySQL and a WordPress container. Uses bind mounts for data persistence. No custom images.
- php_: Simple PHP app, custom Docker image, no persistence.
- *TODO: add more examples...* 

Background
----------

To be honest, I started this project after looking for something similar but somehow failing to find fig_ or `docker compose`_.

When I found out about those two projects, I had written enough code for it to be useable.

I decided to keep on going as while there are a lot of similarities, some aspects are different. My hope is that it turns out to be useful to at least some people ;)


FAQ
---

- **My Docker daemon is running on another host (boot2docker and the like). How can I use rocker in that case?**

  rocker's been designed to support the ``DOCKER_HOST`` variable. However, so far I've only tested UNIX socket connections (and disabled TCP connections by raising an exception), but it shouldn't be too hard to get the TCP version to work.
- **Why JSON and not [insert format here]?**

  JSON was chosen as common denominator. It can be parsed and/or generated by pretty much any language/toolset out there. Plus it's used by Docker's `Remote API`_

  But if you really want an alternative (not a replacement!) and have good arguments, open a GitHub_ issue and make your case.
- **Are there any alternatives**

  While I wasn't aware of that when I originally started this project, there are similar projects. As far as I know fig_ was the first one but has since been replaced by `docker compose`_.



.. _fig: http://www.fig.sh/
.. _docker compose: http://docs.docker.com/compose/
.. _github: https://github.com/mreithub/rocker
.. _pypi: https://pypi.python.org/pypi/rocker
.. _remote api: http://docs.docker.com/reference/api/docker_remote_api_v1.18/
.. _data volume container: https://docs.docker.com/userguide/dockervolumes/#creating-and-mounting-a-data-volume-container

.. _postgres: https://github.com/mreithub/rocker/tree/master/examples/postgres
.. _wordpress: https://github.com/mreithub/rocker/tree/master/examples/wordpress
.. _php: https://github.com/mreithub/rocker/tree/master/examples/phpApp

.. _docker run docs: https://docs.docker.com/reference/run/#runtime-privilege-linux-capabilities-and-lxc-configuration
.. _capabilities manpage: http://man7.org/linux/man-pages/man7/capabilities.7.html