#!/bin/sh
set -eu

if [ ! -f "${APP_CONF}" ]; then
    echo "Missing application config: ${APP_CONF}" >&2
    echo "Mount a production config at /app/config/local.toml." >&2
    exit 64
fi

exec "$@"
