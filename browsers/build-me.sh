#!/bin/bash
# Build image for current browser, using dir name as the image
# to be run from the working dir of the current browser to be built

name=$(basename $PWD)

#docker build -t "netcapsule/$name" .
opt="-t webrecorder/$name:latest"

if [ -a $PWD/tags ]; then
    while read tag; do
        opt="-t webrecorder/$name:$tag $opt"
    done <$PWD/tags
fi

docker build $opt .
echo "Built $opt"

