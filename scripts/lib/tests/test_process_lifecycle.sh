#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${SCRIPT_DIR}/process_lifecycle.sh"

TEST_TMP="$(mktemp -d)"
trap 'rm -rf "${TEST_TMP}"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

expect_failure() {
  if "$@"; then
    fail "expected failure: $*"
  fi
}

write_state() {
  local path="$1"
  printf 'version=1\npid=4242\nboot_id=abcdef12-1234\nstart_time=101\ncommand=hlstats_py.runtime\n' > "${path}"
}

reset_mocks() {
  RUNNING=1
  IDENTITY_RESULT=0
  WAIT_RESULT=0
  SIGNAL_RESULT=0
  SIGNAL_CALLS=""
  hlx_process_is_running() { [ "${RUNNING}" -eq 1 ]; }
  hlx_process_identity_matches_state() { return "${IDENTITY_RESULT}"; }
  hlx_wait_for_owned_exit() { return "${WAIT_RESULT}"; }
  hlx_signal_owned_process() {
    SIGNAL_CALLS="${SIGNAL_CALLS}|$2"
    return "${SIGNAL_RESULT}"
  }
}

test_stale_reused_pid_refuses_without_signal() {
  local pidfile="${TEST_TMP}/reused.pid"
  write_state "${pidfile}"
  reset_mocks
  IDENTITY_RESULT=1

  expect_failure hlx_stop_pid_file "${pidfile}" "test worker" "hlstats_py.runtime" 0
  [ -f "${pidfile}" ] || fail "reused PID state was removed"
  [ -z "${SIGNAL_CALLS}" ] || fail "reused PID was signalled: ${SIGNAL_CALLS}"
}

test_owned_pid_receives_term_and_state_is_removed_after_exit() {
  local pidfile="${TEST_TMP}/owned.pid"
  write_state "${pidfile}"
  reset_mocks

  hlx_stop_pid_file "${pidfile}" "test worker" "hlstats_py.runtime" 0
  [ ! -e "${pidfile}" ] || fail "owned PID state was not removed after exit"
  [ "${SIGNAL_CALLS}" = "|TERM" ] || fail "expected one SIGTERM, got ${SIGNAL_CALLS}"
}

test_malformed_state_refuses_without_cleanup_or_signal() {
  local pidfile="${TEST_TMP}/malformed.pid"
  printf '4242\n' > "${pidfile}"
  reset_mocks

  expect_failure hlx_stop_pid_file "${pidfile}" "test worker" "hlstats_py.runtime" 0
  [ -f "${pidfile}" ] || fail "malformed state was removed"
  [ -z "${SIGNAL_CALLS}" ] || fail "malformed state triggered a signal"
}

test_unreadable_state_refuses_without_cleanup_or_signal() {
  local pidfile="${TEST_TMP}/unreadable.pid"
  write_state "${pidfile}"
  reset_mocks
  hlx_read_pid_state() { return 1; }

  expect_failure hlx_stop_pid_file "${pidfile}" "test worker" "hlstats_py.runtime" 0
  [ -f "${pidfile}" ] || fail "unreadable state was removed"
  [ -z "${SIGNAL_CALLS}" ] || fail "unreadable state triggered a signal"
}

test_term_error_keeps_state_for_attended_recovery() {
  local pidfile="${TEST_TMP}/term-error.pid"
  write_state "${pidfile}"
  reset_mocks
  SIGNAL_RESULT=1

  expect_failure hlx_stop_pid_file "${pidfile}" "test worker" "hlstats_py.runtime" 0
  [ -f "${pidfile}" ] || fail "state was removed after SIGTERM error"
  [ "${SIGNAL_CALLS}" = "|TERM" ] || fail "unexpected signal sequence: ${SIGNAL_CALLS}"
}

test_identity_change_before_escalation_never_sends_sigkill() {
  local pidfile="${TEST_TMP}/escalation-race.pid"
  write_state "${pidfile}"
  reset_mocks
  WAIT_RESULT=1
  local identity_calls=0
  hlx_process_identity_matches_state() {
    identity_calls=$((identity_calls + 1))
    [ "${identity_calls}" -lt 3 ]
  }

  expect_failure hlx_stop_pid_file "${pidfile}" "test worker" "hlstats_py.runtime" 0
  [ -f "${pidfile}" ] || fail "state was removed after identity change"
  [ "${SIGNAL_CALLS}" = "|TERM" ] || fail "SIGKILL was sent after identity change: ${SIGNAL_CALLS}"
}

test_stale_dead_state_is_cleaned_without_signal() {
  local pidfile="${TEST_TMP}/dead.pid"
  write_state "${pidfile}"
  reset_mocks
  RUNNING=0

  hlx_stop_pid_file "${pidfile}" "test worker" "hlstats_py.runtime" 0
  [ ! -e "${pidfile}" ] || fail "dead process state was not cleaned"
  [ -z "${SIGNAL_CALLS}" ] || fail "dead process state triggered a signal"
}

test_missing_linux_identity_support_refuses_managed_pid_state() {
  local pidfile="${TEST_TMP}/unsupported-platform.pid"
  local previous_proc_root="${HLX_PROC_ROOT}"
  HLX_PROC_ROOT="${TEST_TMP}/no-procfs"

  expect_failure hlx_identity_platform_supported
  expect_failure hlx_write_pid_file "${pidfile}" 4242 "hlstats_py.runtime"
  [ ! -e "${pidfile}" ] || fail "unsupported platform wrote managed PID state"
  HLX_PROC_ROOT="${previous_proc_root}"
}

test_launchers_refuse_without_linux_identity_support() {
  local launcher_dir="${TEST_TMP}/unsupported-launchers"
  local proc_root="${launcher_dir}/no-procfs"
  local output
  mkdir -p "${launcher_dir}"
  : > "${launcher_dir}/hlstats.conf"

  output="$(cd "${launcher_dir}" && HLX_PROC_ROOT="${proc_root}" bash "${SCRIPT_DIR}/../run_hlstats_py" start 1 28000 1 2>&1)" \
    && fail "hlstats launcher started without Linux identity support"
  [[ "${output}" == *"Linux procfs identity checks are unavailable"* ]] \
    || fail "hlstats launcher refusal was unclear: ${output}"

  output="$(cd "${launcher_dir}" && HLX_PROC_ROOT="${proc_root}" bash "${SCRIPT_DIR}/../run_proxy_py" start 2>&1)" \
    && fail "proxy launcher started without Linux identity support"
  [[ "${output}" == *"Linux procfs identity checks are unavailable"* ]] \
    || fail "proxy launcher refusal was unclear: ${output}"
}

test_stale_reused_pid_refuses_without_signal
test_owned_pid_receives_term_and_state_is_removed_after_exit
test_malformed_state_refuses_without_cleanup_or_signal
test_term_error_keeps_state_for_attended_recovery
test_identity_change_before_escalation_never_sends_sigkill
test_stale_dead_state_is_cleaned_without_signal
test_missing_linux_identity_support_refuses_managed_pid_state
test_launchers_refuse_without_linux_identity_support
test_unreadable_state_refuses_without_cleanup_or_signal

echo "process lifecycle tests passed"
