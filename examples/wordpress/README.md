Simple wordpress blog
=====================

This example project shows how to set up wordpress and a mysql database.

For simplicity, we won't use data volume containers here (we'd need an extra container for wordpress and another one for mysql) but will use simple rocker-backed host volumes instead.

For an example on data volume containers have a look at the `postgres` example.

Container config
----------------

Wordpress stores most of its data in a MySQL database. Therefore, we'll create a container config for MySQL (and save it as `mysql-wp.rocker`):

```json
{
    "image": "mysql",
    "env": {
        "MYSQL_ROOT_PASSWORD": "hackme"
    },
    "volumes": [
        { "src": "mysql/", "tgt": "/var/lib/mysql" }
    ]
}
```

The container uses the official ['mysql' Docker image][1].

We specify the environment variable `MYSQL_ROOT_PASSWORD` to set the database password.

And we declare a host based volume (i.e. a bind mount) for `/var/lib/mysql` (the directory MySQL uses to store its databases).  
As `mysql/` is a relative path, rocker will translate it to `/docker/mysql-wp/mysql/`.


Time to look at the wordpress container config (named `blog.rocker`):

```json
{
	"image": "wordpress",
	"links": {
		"mysql": "mysql-wp"
	},
	"ports": [ 80 ],
	"volumes": [
		{"src": "www", "tgt": "/var/www/html"}
	]
}
```

It uses the official ['wordpress' image][2].

It links to the `mysql-wp` container (with the alias `mysql`). The wordpress image uses the variable `WORDPRESS_DB_HOST` to find the database. That variable defaults to `mysql`, so by using the alias `mysql` for our link, we don't have to explicitly set the `WORDPRESS_DB_HOST` variable.

We also tell Docker to forward requests to port 80 to our container.

And we'll define a bind-mount to keep the container's `/var/www/html/` directory persistent (as that's where wordpress will store all the uploaded files, etc.)

Startup
-------

Simply issue

    rocker run blog

This will cause rocker to create and start the `blog` and `mysql-wp` containers.

[1]: https://registry.hub.docker.com/_/mysql/
[2]: https://registry.hub.docker.com/_/wordpress/