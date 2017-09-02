#!/bin/bash

set -e

if ! which -s docker; then
    echo "docker executable not found. Aborting!"
    exit 1
fi

if [[ -z "${1}" ]]; then
    echo "Missing required positional argument ENV_NAME, the name of the environment to run the test on"
    exit 1
fi
ENV_NAME="${1}"

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
sleep 1
run_tests
exit "${?}"
