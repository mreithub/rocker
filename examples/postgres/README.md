Standalone PostgreSQL server
============================

This example project shows you how to setup a postgresql server inside docker.

It uses the official `postgres` docker image which specifies a volume at `/var/lib/postgresql/data`.
We'll create an extra `postgres-data` container which will serve as persistent data container for that volume.

That way we can replace the `postgres` container (e.g. upgrade to a newer version) without losing data.

Read [Docker's documentation on volume containers][2] for more information on the topic.

`postgres-data.rocker`
----------------------

    {
        "image": "postgres",
        "entrypoint": ["echo", "Data container for the postgres container"]
    }

We replace the image's default entry point by a simple message.  
That way, when you try to run the container it will stop again immediately, simply printing a log message that can be seen when issuing `docker logs postgres-data`.

`postgres.rocker`
-----------------

    {
        "image": "postgres",
        "volumesFrom": "postgres-data"
    }

This container will hold the actual PostgreSQL server.  
The `volumesFrom` directive tells Docker to add all the volumes of `postgres-data` to the `postgres` container.

This only works because the official [`postgres` Dockerfile][1] already specifies Postgres' data directory as volume. If it didn't, we'd have to add a `"volume": "/var/lib/postgresql/data"` directive to our `postgres-data.rocker`.

rocker implicitly adds all the containers specified in a `volumesFrom` directive to the list of dependencies for that container and will therefore create/run `postgres-data` before `postgres`.


Running rocker
--------------

You can create and run the above containers by issuing

    rocker run postgres

in the project directory.

That call implicitly launches `rocker run postgres-data` before creating the actual `postgres` container


[1]: https://github.com/docker-library/postgres/blob/bfca9b8a92a99ccfc8f04933b7ecc29a108c7f49/9.4/Dockerfile
[2]: https://docs.docker.com/userguide/dockervolumes/#creating-and-mounting-a-data-volume-container
