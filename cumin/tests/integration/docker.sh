#!/bin/bash

set -e

if ! which docker &> /dev/null; then
    echo "docker executable not found. Aborting!"
    exit 1
fi

if [[ -z "${1}" ]]; then
    echo "Missing required positional argument ENV_NAME, the name of the environment to run the test on"
    exit 1
fi
ENV_NAME="${1}"
SKIP_DELETION=0
if [[ -n "${2}" && "${2}" -eq "1" ]]; then
    SKIP_DELETION=1
fi

ENV_FILE="$(dirname "${0}")/${ENV_NAME}.sh"
if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Environment file '${ENV_FILE}' not found. Aborting!"
    exit 1
fi

function _log() {
    echo "$(date +"%F %T") | ${*}"
}

# shellcheck source=/dev/null
source "${ENV_FILE}"

# The sourced ENV_FILE must register any docker instance in this variable for cleanup
DOCKER_INSTANCES=""
function exit_trap() {
    if [[ "${SKIP_DELETION}" -eq "1" ]]; then
        _log "Skip deletion set: docker instances and temporary directory were not removed"
        return
    fi

    _log "Removing docker instances"
    docker rm -f ${DOCKER_INSTANCES} > /dev/null

    if [[ -n "${CUMIN_TMPDIR}" ]]; then
        _log "Cleaning TMPDIR: ${CUMIN_TMPDIR}"
        rm -rf "${CUMIN_TMPDIR}"
    fi
}


export CUMIN_TMPDIR
export CUMIN_IDENTIFIER
CUMIN_TMPDIR="$(mktemp -d /tmp/cumin-XXXXXX)"
_log "Temporary directory is: ${CUMIN_TMPDIR}"
CUMIN_IDENTIFIER="$(basename "${CUMIN_TMPDIR}")"
_log "Unique identifier is ${CUMIN_IDENTIFIER}"

trap 'exit_trap' EXIT

setup
sleep 3
run_tests
exit "${?}"
