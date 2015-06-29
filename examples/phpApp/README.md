Simple PHP site
===============

This is the first example using a custom image.
It shows a pretty minimalistic, not very well written PHP website that tracks its users.

It's the first example actually using a custom image (derived from the official `php:apache` image).

It contains a simple `index.php` as well as a `phpinfo.php` file.

In practise you'd use some form of persistent volumes (a data container or bind mount). But to keep this example simple, we skipped that part (see the `wordpress/` or `mysql/` examples for details on how to use them).

Project structure
-------------------

    myHp.rocker
    homepage/
      Dockerfile
      index.php
      phpinfo.php

rocker expects its projects to have a certain directory structure.

All container configurations (`.rocker` files) are expected to be in the project's root path.  
The file name is used as container name.

Each image has its own directory. rocker looks for `{imageName}/Dockerfile` to determine if an image exists locally or has to be pulled.

Local images will be rebuilt if files have changed.


Dockerfile
----------

```
FROM php:apache

COPY . /var/www/html/

# Docker will create the volume dir with the owner set to root. To fix that, we'll create the folder manually
RUN install --owner www-data -d /var/www/html/data/
VOLUME /var/www/html/data/
```

Our image builds upon the official `php:apache` image.

It simply copies all the files in the `homepage/` directory into the image's `/var/www/html/` directory.

It also declares a volume (and makes sure php can write to it).

Container config
----------------

```
myHp.rocker:
{
	"image": "homepage",
	"ports": [80]
}
```

Our container uses the image `homepage`, therefore rocker looks for the file `homepage/Dockerfile`.  
As that file exists, it will build the image before creating the container.

Also, it exposes port 80.

Startup
-------

Issue `rocker run myHp` to start the container.  
rocker will (re)build the underlying image automatically if necessary.

After the container has been started, visit http://localhost/ to see the site in action.
