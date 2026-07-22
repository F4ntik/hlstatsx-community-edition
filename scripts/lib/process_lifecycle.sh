#!/usr/bin/env bash

set -euo pipefail

HLX_STOP_TIMEOUT="${HLX_STOP_TIMEOUT:-10}"
HLX_STOP_POLL_INTERVAL="${HLX_STOP_POLL_INTERVAL:-1}"
# Overridable only for focused tests. Production requires Linux procfs.
HLX_PROC_ROOT="${HLX_PROC_ROOT:-/proc}"
HLX_LIFECYCLE_PYTHON="${HLX_LIFECYCLE_PYTHON:-python3}"

HLX_PID_STATE_PID=""
HLX_PID_STATE_BOOT_ID=""
HLX_PID_STATE_START_TIME=""
HLX_PID_STATE_COMMAND=""

hlx_identity_platform_supported() {
  [ -r "${HLX_PROC_ROOT}/sys/kernel/random/boot_id" ] \
    && [ -r "${HLX_PROC_ROOT}/self/stat" ] \
    && [ -r "${HLX_PROC_ROOT}/self/cmdline" ] \
    && "${HLX_LIFECYCLE_PYTHON}" -c 'import os, signal; assert hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal")' >/dev/null 2>&1
}

hlx_clear_pid_state() {
  HLX_PID_STATE_PID=""
  HLX_PID_STATE_BOOT_ID=""
  HLX_PID_STATE_START_TIME=""
  HLX_PID_STATE_COMMAND=""
}

hlx_read_pid_state() {
  local pidfile="$1"
  local line key value
  local have_version=0 have_pid=0 have_boot_id=0 have_start_time=0 have_command=0

  hlx_clear_pid_state
  [ -r "${pidfile}" ] || return 1

  while IFS= read -r line || [ -n "${line}" ]; do
    case "${line}" in
      version=*)
        [ "${have_version}" -eq 0 ] || return 1
        value="${line#version=}"
        [ "${value}" = "1" ] || return 1
        have_version=1
        ;;
      pid=*)
        [ "${have_pid}" -eq 0 ] || return 1
        HLX_PID_STATE_PID="${line#pid=}"
        have_pid=1
        ;;
      boot_id=*)
        [ "${have_boot_id}" -eq 0 ] || return 1
        HLX_PID_STATE_BOOT_ID="${line#boot_id=}"
        have_boot_id=1
        ;;
      start_time=*)
        [ "${have_start_time}" -eq 0 ] || return 1
        HLX_PID_STATE_START_TIME="${line#start_time=}"
        have_start_time=1
        ;;
      command=*)
        [ "${have_command}" -eq 0 ] || return 1
        HLX_PID_STATE_COMMAND="${line#command=}"
        have_command=1
        ;;
      *) return 1 ;;
    esac
  done < "${pidfile}" || return 1

  [ "${have_version}" -eq 1 ] && [ "${have_pid}" -eq 1 ] \
    && [ "${have_boot_id}" -eq 1 ] && [ "${have_start_time}" -eq 1 ] \
    && [ "${have_command}" -eq 1 ] \
    && [[ "${HLX_PID_STATE_PID}" =~ ^[1-9][0-9]*$ ]] \
    && [[ "${HLX_PID_STATE_BOOT_ID}" =~ ^[0-9A-Fa-f-]+$ ]] \
    && [[ "${HLX_PID_STATE_START_TIME}" =~ ^[0-9]+$ ]] \
    && [[ "${HLX_PID_STATE_COMMAND}" =~ ^[A-Za-z0-9_.-]+$ ]]
}

# Compatibility helper for callers that only need the PID after the state has
# passed structural validation. It intentionally rejects legacy bare-PID files.
hlx_read_pid_file() {
  hlx_read_pid_state "$1" || return 1
  printf '%s\n' "${HLX_PID_STATE_PID}"
}

hlx_read_process_start_time() {
  local pid="$1"
  local stat_file="${HLX_PROC_ROOT}/${pid}/stat"

  [ -r "${stat_file}" ] || return 1
  # After removing fields 1-2 (pid and parenthesized comm), field 20 is the
  # kernel start time (original proc stat field 22).
  awk '{ sub(/^.*\\) /, ""); print $20 }' "${stat_file}" 2>/dev/null \
    | { read -r value; [[ "${value}" =~ ^[0-9]+$ ]]; }
}

hlx_process_has_command() {
  local pid="$1"
  local expected_command="$2"
  local cmdline_file="${HLX_PROC_ROOT}/${pid}/cmdline"

  [ -r "${cmdline_file}" ] || return 1
  tr '\0' '\n' < "${cmdline_file}" | grep -Fqx -- "${expected_command}"
}

hlx_process_is_running() {
  local pid="$1"
  kill -0 "${pid}" >/dev/null 2>&1
}

hlx_process_identity_matches_state() {
  local expected_command="$1"
  local start_time
  local boot_id

  [ "${HLX_PID_STATE_COMMAND}" = "${expected_command}" ] || return 1
  hlx_process_is_running "${HLX_PID_STATE_PID}" || return 1
  hlx_identity_platform_supported || return 1
  boot_id="$(cat "${HLX_PROC_ROOT}/sys/kernel/random/boot_id" 2>/dev/null || true)"
  [ "${boot_id}" = "${HLX_PID_STATE_BOOT_ID}" ] || return 1
  start_time="$(hlx_read_process_start_time "${HLX_PID_STATE_PID}" || true)"
  [ "${start_time}" = "${HLX_PID_STATE_START_TIME}" ] || return 1
  hlx_process_has_command "${HLX_PID_STATE_PID}" "${expected_command}"
}

hlx_signal_owned_process() {
  local expected_command="$1"
  local signal_name="$2"

  "${HLX_LIFECYCLE_PYTHON}" - "${HLX_PROC_ROOT}" "${HLX_PID_STATE_PID}" \
    "${HLX_PID_STATE_BOOT_ID}" "${HLX_PID_STATE_START_TIME}" "${expected_command}" \
    "${signal_name}" <<'PY'
import os
import signal
import sys

proc_root, raw_pid, expected_boot_id, expected_start_time, expected_command, signal_name = sys.argv[1:]
pid = int(raw_pid)
pidfd = os.pidfd_open(pid)
try:
    boot_id = open(os.path.join(proc_root, "sys/kernel/random/boot_id"), encoding="utf-8").read().strip()
    stat = open(os.path.join(proc_root, str(pid), "stat"), encoding="utf-8").read()
    fields = stat.rsplit(") ", 1)[1].split()
    start_time = fields[19]
    command_line = open(os.path.join(proc_root, str(pid), "cmdline"), "rb").read().split(b"\0")
    if (boot_id != expected_boot_id or start_time != expected_start_time
            or expected_command.encode("utf-8") not in command_line):
        raise RuntimeError("process identity mismatch")
    signal.pidfd_send_signal(pidfd, getattr(signal, signal_name))
finally:
    os.close(pidfd)
PY
}

hlx_pid_file_status() {
  local pidfile="$1"
  local expected_command="$2"

  [ -f "${pidfile}" ] || return 1
  hlx_read_pid_state "${pidfile}" || return 2
  hlx_process_is_running "${HLX_PID_STATE_PID}" || return 1
  hlx_process_identity_matches_state "${expected_command}" || return 2
}

hlx_write_pid_file() {
  local pidfile="$1"
  local pid="$2"
  local expected_command="$3"
  local boot_id start_time tmpfile

  hlx_identity_platform_supported || return 1
  boot_id="$(cat "${HLX_PROC_ROOT}/sys/kernel/random/boot_id")"
  start_time="$(hlx_read_process_start_time "${pid}")" || return 1
  hlx_process_is_running "${pid}" || return 1
  hlx_process_has_command "${pid}" "${expected_command}" || return 1

  umask 077
  tmpfile="$(mktemp "${pidfile}.tmp.XXXXXX")" || return 1
  printf 'version=1\npid=%s\nboot_id=%s\nstart_time=%s\ncommand=%s\n' \
    "${pid}" "${boot_id}" "${start_time}" "${expected_command}" > "${tmpfile}" \
    || { rm -f "${tmpfile}"; return 1; }
  mv -f "${tmpfile}" "${pidfile}"
}

hlx_remove_stale_pid_file() {
  local pidfile="$1"
  local label="$2"

  rm -f "${pidfile}" || return 1
  echo "Removed stale ${label} pid file"
}

hlx_prepare_pid_file_for_start() {
  local pidfile="$1"
  local label="$2"
  local expected_command="$3"
  local status

  [ -f "${pidfile}" ] || return 0
  if hlx_pid_file_status "${pidfile}" "${expected_command}"; then
    echo "${label} is already running"
    return 2
  fi
  status=$?
  if [ "${status}" -eq 1 ]; then
    hlx_remove_stale_pid_file "${pidfile}" "${label}"
    return 0
  fi

  echo "Refusing to replace ${label} pid file: process ownership cannot be proven" >&2
  return 1
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
}

hlx_wait_for_owned_exit() {
  local expected_command="$1"
  local timeout="$2"
  local elapsed=0

  while hlx_process_is_running "${HLX_PID_STATE_PID}"; do
    hlx_process_identity_matches_state "${expected_command}" || return 2
    if [ "${elapsed}" -ge "${timeout}" ]; then
      return 1
    fi
    sleep "${HLX_STOP_POLL_INTERVAL}"
    elapsed=$((elapsed + HLX_STOP_POLL_INTERVAL))
  done
}

hlx_stop_pid_file() {
  local pidfile="$1"
  local label="$2"
  local expected_command="$3"
  local timeout="${4:-${HLX_STOP_TIMEOUT}}"
  local status wait_status

  if [ ! -f "${pidfile}" ]; then
    echo "${label} is not running"
    return 0
  fi

  if hlx_pid_file_status "${pidfile}" "${expected_command}"; then
    :
  else
    status=$?
    if [ "${status}" -eq 1 ]; then
      hlx_remove_stale_pid_file "${pidfile}" "${label}"
      return 0
    fi
    echo "Refusing to stop ${label}: process ownership cannot be proven" >&2
    return 1
  fi

  # Recheck immediately before every signal. A mismatch is fail-closed.
  hlx_process_identity_matches_state "${expected_command}" || {
    echo "Refusing to stop ${label}: process identity changed" >&2
    return 1
  }
  if ! hlx_signal_owned_process "${expected_command}" TERM >/dev/null 2>&1; then
    echo "Refusing to remove ${label} pid file: SIGTERM failed" >&2
    return 1
  fi

  if hlx_wait_for_owned_exit "${expected_command}" "${timeout}"; then
    hlx_remove_stale_pid_file "${pidfile}" "${label}"
    echo "Stopped ${label}"
    return 0
  fi
  wait_status=$?
  if [ "${wait_status}" -eq 2 ]; then
    echo "Refusing to escalate ${label}: process identity changed" >&2
    return 1
  fi

  hlx_process_identity_matches_state "${expected_command}" || {
    echo "Refusing to escalate ${label}: process identity changed" >&2
    return 1
  }
  echo "${label} did not stop within ${timeout}s; sending SIGKILL"
  if ! hlx_signal_owned_process "${expected_command}" KILL >/dev/null 2>&1; then
    echo "Refusing to remove ${label} pid file: SIGKILL failed" >&2
    return 1
  fi
  if hlx_wait_for_owned_exit "${expected_command}" "${timeout}"; then
    hlx_remove_stale_pid_file "${pidfile}" "${label}"
    echo "Stopped ${label}"
    return 0
  fi
  wait_status=$?
  if [ "${wait_status}" -eq 2 ]; then
    echo "Refusing to remove ${label} pid file: process identity changed" >&2
  else
    echo "Refusing to remove ${label} pid file: process did not exit" >&2
  fi
  return 1
}
