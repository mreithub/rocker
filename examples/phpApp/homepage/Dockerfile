FROM php:apache

COPY . /var/www/html/

# Docker will create the volume dir with the owner set to root. To fix that, we'll create the folder manually
RUN install --owner www-data -d /var/www/html/data/
VOLUME /var/www/html/data/

