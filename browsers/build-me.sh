#!/bin/bash
# Build image for current browser, using dir name as the image
# to be run from the working dir of the current browser to be built

name=$(basename $PWD)

opt=""

if [ -a $PWD/docker-compose.yml ]; then
  docker-compose build
  exit 0
fi

if [ ! -f "$PWD/tags" ]; then
    opt="-t oldwebtoday/$name"
fi

if [ -a $PWD/tags ]; then
    while read tag; do
        opt="-t oldwebtoday/$tag $opt"
    done <$PWD/tags
fi

docker build $opt .
echo "Built $opt"

