#!/bin/bash
# CLI output comparison tests between versions helper script.
# Refer to the related paragraph in the Development page of the documentation for the instructions on how to run them.
# Requirements:
# - icdiff
# - csplit (coreutils)

NEW='new'
OLD='old'

if [[ -d "${OLD}/" || -d "${NEW}/" ]]; then
    echo "Directory ${OLD} or ${NEW} already existing, aborting comparison."
    exit 1
fi

mkdir "${OLD}/" "${NEW}/"
cd "${OLD}/" || exit 1
csplit -ksf out -n 3 ../old.out '/### test_/' '{1000}'
cd "../${NEW}/" || exit 1
csplit -ksf out -n 3 ../new.out '/### test_/' '{1000}'
cd "../"

if ! icdiff --no-headers <(ls -1 ${OLD}/) <(ls -1 ${NEW}/); then
    echo "The list of test files between ${OLD}/ and ${NEW}/ differs, aborting comparison."
    exit 1
fi

for file in "${OLD}"/*; do
    file="$(basename "${file}")"
    file_diff="$(icdiff -HN --whole-file --color-map='separator:yellow_bold' "${OLD}/${file}" "${NEW}/${file}")"
    file_diff_exit="${?}"
    sorted_diff="$(icdiff -HU 0 --color-map='separator:yellow_bold' <(sort "${OLD}/${file}") <(sort "${NEW}/${file}"))"
    sorted_diff_exit="${?}"

    if [[ "${file_diff_exit}" -eq "0" ]]; then
        echo "Files ${OLD}/${file} and ${NEW}/${file} are identical."
    elif [[ "${sorted_diff_exit}" -eq "0" ]]; then
        echo "Files ${OLD}/${file} and ${NEW}/${file} differs just in line ordering."
    else
        echo "Files ${OLD}/${file} and ${NEW}/${file} differ:"
        echo "${file_diff}"
        echo -e "\033[31;43m-----------------------------------------------------------------------------------------\033[0m"
        echo "Files ${OLD}/${file} and ${NEW}/${file} sorted diff:"
        echo "${sorted_diff}"
        echo -e "\033[31;43m=========================================================================================\033[0m"
    fi
done
