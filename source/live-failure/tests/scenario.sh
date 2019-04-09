#!/bin/bash

set -o errexit

LOGFILE=automation-agent.log
CONFIG_FILE=test-config.json

# copy the real script into a test script that we can modify
cp configs/replset-initial.json $CONFIG_FILE

# The goal for this script:

# 1. Launch the agent forked, get the process id
echo "Launching the automation agent."
./mongodb-mms-automation-agent -cluster $CONFIG_FILE &> $LOGFILE &
AGENT_PID=$!

# 2. Detect when all processes are set up
until grep -q "All 3 Mongo processes are in goal state" $LOGFILE; do
    echo "Waiting for cluster to come online..."
    sleep 2
done

echo "" > $LOGFILE

# 3. Restart one of the servers (for now; later we'll restart each of them in sequence).
RESTART_DATE=`date -u '+%Y-%m-%dT%TZ'`
sed "s/<LAST_RESTART_PLACEHOLDER>/$RESTART_DATE/" configs/replset-restart1-template.json > $CONFIG_FILE

# 4. Detect when the scenario has finished.
until grep -q "All 3 Mongo processes are in goal state" $LOGFILE; do
    echo "Waiting for scenario to complete..."
    sleep 2
done

# 5. Kill the agent and the servers
echo "Scenario complete."
echo "Killing the automation agent."
kill $AGENT_PID
killall mongod

# 5. Clean up and exit
rm $LOGFILE
rm $CONFIG_FILE
