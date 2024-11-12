#!/bin/bash

set -e

SSH_KEY_ALGO='ed25519'

function setup() {
    ssh-keygen -t ${SSH_KEY_ALGO} -N "" -f "${CUMIN_TMPDIR}/id_${SSH_KEY_ALGO}" -C "cumin-integration-tests" > /dev/null
    cat <<EOF > "${CUMIN_TMPDIR}/config.yaml"
default_backend: direct
transport: clustershell
log_file: ${CUMIN_TMPDIR}/cumin.log

clustershell:
    ssh_options:
        - '-F ${CUMIN_TMPDIR}/ssh_config'
    fanout: 3
EOF

    local SSH_ALIASES=""
    _log "Creating docker instances"
    for index in {1..5}; do
        HOST_NAME="${CUMIN_IDENTIFIER}-${index}"
        # TODO: use a custom-generated image
        docker run -d -p "222${index}:2222" -e PUBLIC_KEY="$(cat ${CUMIN_TMPDIR}/id_${SSH_KEY_ALGO}.pub)" \
            -e USER_NAME=cumin -e SUDO_ACCESS=true --hostname "${HOST_NAME}" --name "${HOST_NAME}" \
            "linuxserver/openssh-server:latest" > /dev/null
        DOCKER_INSTANCES="${DOCKER_INSTANCES} ${HOST_NAME}"
        SSH_ALIASES="${SSH_ALIASES}
Host ${HOST_NAME}
    Port 222${index}
"
    done

    cat <<EOF > "${CUMIN_TMPDIR}/ssh_config"
Host *
    User cumin
    Hostname localhost
    IdentityFile ${CUMIN_TMPDIR}/id_${SSH_KEY_ALGO}
    IdentitiesOnly yes
    LogLevel QUIET
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null

${SSH_ALIASES}
EOF

    _log "Created docker instances: ${DOCKER_INSTANCES}"
}

function run_tests() {
    sleep 5  # Make sure all SSH servers are up and running
    cumin --force -c "${CUMIN_TMPDIR}/config.yaml" "${CUMIN_IDENTIFIER}-[1-2,5]" "touch /tmp/maybe"
    cumin --force -c "${CUMIN_TMPDIR}/config.yaml" "${CUMIN_IDENTIFIER}-[1-5]" 'echo -e "First\nSecond\nThird" > /tmp/out'
    py.test -n auto --strict-markers --cov-report term-missing --cov=cumin cumin/tests/integration
}
