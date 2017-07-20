#!/bin/bash

set -e

function setup() {
    ssh-keygen -t ed25519 -N "" -f "${CUMIN_TMPDIR}/id_rsa" -C "cumin-integration-tests" > /dev/null
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
        docker run -d -p "222${index}:22" -v "/${CUMIN_TMPDIR}/id_rsa.pub:/root/.ssh/authorized_keys" --name "${HOST_NAME}" "macropin/sshd" > /dev/null
        DOCKER_INSTANCES="${DOCKER_INSTANCES} ${HOST_NAME}"
        SSH_ALIASES="${SSH_ALIASES}
Host ${HOST_NAME}
    Hostname localhost
    Port 222${index}
"
    done

    cat <<EOF > "${CUMIN_TMPDIR}/ssh_config"
Host *
    User root
    IdentityFile ${CUMIN_TMPDIR}/id_rsa
    IdentitiesOnly yes
    LogLevel QUIET
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null

${SSH_ALIASES}
EOF

    _log "Created docker instances:${DOCKER_INSTANCES}"
}

function run_tests() {
    USER=root SUDO_USER=user cumin --force -c "${CUMIN_TMPDIR}/config.yaml" "${CUMIN_IDENTIFIER}-[1-2,5]" "touch /tmp/maybe" > /dev/null 2>&1
    py.test -n auto --strict --cov-report term-missing --cov=cumin cumin/tests/integration
}
