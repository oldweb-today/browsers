#!/bin/bash

# Detect if git-lfs is installed (For Chrome and Wine)
set +e
git lfs  &> /dev/null
if [ $? -ne 0 ]; then
    echo 'Error: git-lfs is not installed.'
    exit 2
fi

set -e
git pull origin master --recurse-submodules
git submodule update --init --remote --merge
