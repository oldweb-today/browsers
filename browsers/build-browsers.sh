#!/bin/bash
DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

set -e

for dir in $DIR/*/
do
    dir=${dir%*/}
    name=`basename $dir`
    if [ -f "$dir/skip" ]; then
       continue
    fi

    cd $dir
    $DIR/build-me.sh
done


