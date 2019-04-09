#!/bin/bash

set -o errexit

# Log file for the automation agent. This is used by the script to detect when the automation agent
# has finished updating the cluster based on the config file changes.
LOGFILE=automation-agent.log

# Location of the config file that the agent is watching. Changes are made to the cluster by copying
# different config files into this location.
CONFIG_FILE=test-config.json

# Location of database directories of the mongod processes. Note that any changes here must also be
# made in the invididual `configs` files as well.
DATA_DIR=/tmp/mms-automation/data 

# Helper function to wait until the automation agent has finished making changes. This will clear
# the log file after completion to ensure that future invocations don't detect the previous
# completion message.
#
# Arguments:
#
# $1 - message to print periodically while waiting for the automation agent to finish
wait_for_agent() {
    until grep -q "All 3 Mongo processes are in goal state" "$LOGFILE"; do
        echo "$1"
        sleep 2
    done

    # Clear logs
    echo "" > "$LOGFILE"
}

# Clear out previous data
rm -rf "$DATA_DIR"

# Copy the initial configuration into the location the agent expects.
cp configs/replset-initial.json "$CONFIG_FILE"

# Launch the agent forked, get the process id
echo "Launching the automation agent...."
mongodb-mms-automation-agent -cluster "$CONFIG_FILE" &> "$LOGFILE" &
AGENT_PID=$!

# Detect when all processes are set up
wait_for_agent "Waiting for cluster to come online..."

# Restart the servers
CURRENT_TIME=`date -u '+%Y-%m-%dT%TZ'`
sed "s/<LAST_RESTART_PLACEHOLDER>/$CURRENT_TIME/" configs/replset-restart-template.json > "$CONFIG_FILE"

# Detect when the scenario has finished
wait_for_agent "Waiting for scenario to complete..."

# Shut down the cluster
cp configs/replset-shutdown.json "$CONFIG_FILE"

# Detect when the cluster has finished shutting down
wait_for_agent "Waiting for cluster to shut down..."

# 6. Kill the agent and the servers
echo "Scenario complete."
echo "Killing the automation agent."
kill $AGENT_PID

# 7. Clean up and exit
rm "$LOGFILE"
rm "$CONFIG_FILE"
