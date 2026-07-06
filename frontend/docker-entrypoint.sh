#!/bin/sh
set -eu

DESIGN_SYSTEM_UPSTREAM="${DESIGN_SYSTEM_UPSTREAM:-http://host.docker.internal:40001}"
DESIGN_SYSTEM_HOST="${DESIGN_SYSTEM_HOST:-host.docker.internal:40001}"

export DESIGN_SYSTEM_UPSTREAM DESIGN_SYSTEM_HOST

envsubst '${DESIGN_SYSTEM_UPSTREAM} ${DESIGN_SYSTEM_HOST}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/http.d/default.conf

exec nginx -g 'daemon off;'
