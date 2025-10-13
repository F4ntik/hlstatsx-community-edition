#!/bin/sh
set -eu

# Ensure the hlstats account uses mysql_native_password while preserving the
# password configured via MYSQL_PASSWORD (or falling back to the default).
mysql_password="${MYSQL_PASSWORD:-hlstats}"
root_password="${MYSQL_ROOT_PASSWORD:-}"

if [ -z "${root_password}" ]; then
  echo "MYSQL_ROOT_PASSWORD must be set for auth plugin adjustment" >&2
  exit 1
fi

# Escape single quotes for SQL literal usage.
escaped_password=$(printf "%s" "${mysql_password}" | sed "s/'/''/g")

mysql --protocol=socket -uroot -p"${root_password}" <<SQL
ALTER USER 'hlstats'@'%' IDENTIFIED WITH mysql_native_password BY '${escaped_password}';
SQL
