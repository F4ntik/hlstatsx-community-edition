#!/usr/bin/env bash

set -euo pipefail

HLX_STOP_TIMEOUT="${HLX_STOP_TIMEOUT:-10}"
HLX_STOP_POLL_INTERVAL="${HLX_STOP_POLL_INTERVAL:-1}"

hlx_read_pid_file() {
  local pidfile="$1"
  local pid

  pid="$(cat "${pidfile}" 2>/dev/null || true)"
  if [[ ! "${pid}" =~ ^[0-9]+$ ]]; then
    return 1
  fi
  printf '%s\n' "${pid}"
}

hlx_process_is_running() {
  local pid="$1"
  kill -0 "${pid}" >/dev/null 2>&1
}

hlx_wait_for_exit() {
  local pid="$1"
  local timeout="$2"
  local elapsed=0

  while hlx_process_is_running "${pid}"; do
    if [ "${elapsed}" -ge "${timeout}" ]; then
      return 1
    fi
    sleep "${HLX_STOP_POLL_INTERVAL}"
    elapsed=$((elapsed + HLX_STOP_POLL_INTERVAL))
  done

  return 0
}

hlx_stop_pid_file() {
  local pidfile="$1"
  local label="$2"
  local timeout="${3:-${HLX_STOP_TIMEOUT}}"
  local pid

  if [ ! -f "${pidfile}" ]; then
    echo "${label} is not running"
    return 0
  fi

  if ! pid="$(hlx_read_pid_file "${pidfile}")"; then
    rm -f "${pidfile}"
    echo "Removed stale ${label} pid file"
    return 0
  fi

  if ! hlx_process_is_running "${pid}"; then
    rm -f "${pidfile}"
    echo "Removed stale ${label} pid file"
    return 0
  fi

  kill "${pid}" >/dev/null 2>&1 || true
  if ! hlx_wait_for_exit "${pid}" "${timeout}"; then
    echo "${label} did not stop within ${timeout}s; sending SIGKILL"
    kill -KILL "${pid}" >/dev/null 2>&1 || true
    hlx_wait_for_exit "${pid}" "${timeout}" || true
  fi

  rm -f "${pidfile}"
  echo "Stopped ${label}"
}
