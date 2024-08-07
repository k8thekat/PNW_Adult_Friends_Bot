#!/bin/bash
SERVICE="pnwbot/main.py"
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
echo $SCRIPT_DIR
cd $SCRIPT_DIR
if test -f ${SERVICE}.pid; then
    if ps -p `cat ${SERVICE}.pid` >/dev/null; then
        echo "${SERVICE} is already running"
        exit 0
    fi
fi

python -u ./${SERVICE} >/dev/null &
echo $! > ${SERVICE}.pid
echo "${SERVICE} is starting"