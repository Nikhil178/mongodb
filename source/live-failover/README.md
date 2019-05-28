Live Failover Tests
===================

This document describes usage for the Live Failover test suite.

In this directory, you will find a script called ``live-failover.py``. This script is designed to be used by drivers to run the live failover tests.

In the ``/configs`` directory you will find a number of json files. ``live-failover.py`` should be run one time for each config file in the ``/configs`` directory.  While ``live-failover.py`` is running, the driver should run specified workloads against the cluster described in the json file (see spec, TODO link).

Running the live-failover.py script
-----------------------------------

The ``live-failover.py`` script operates in three stages represented by three distinct commands:

* `start` - launch a mongo cluster matching the given config file (via the automation agent)

* `scenario` - put the cluster through a series of restarts (via the automation agent)

* `stop` - spin down the cluster (and the automation agent)

For each stage the script should be run like so:

    python live-failover.py <cmd> <path/to/config/file> --additional args

Use `--help` for more information.