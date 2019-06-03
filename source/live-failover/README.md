Live Failover Tests
===================

This document describes usage for the Live Failover test suite.

In this directory, you will find a script called ``live-failover.py``. This script is designed to be used by drivers to run the live failover tests.

Requirements
------------

The ``live-failover.py`` script requires python 3.

The script also requires that the binary for the automation agent be in an executable called ``mongodb-mms-automation-agent`` in the working directory.

Running the live-failover.py script
-----------------------------------

The ``live-failover.py`` script operates in three stages represented by three distinct commands:

* `start` - launch a mongo cluster matching the given config file (via the automation agent):

   ``python live-failover.py start <path/to/config/file>``

* `scenario` - put the cluster through a series of restarts (via the automation agent) using a simulated server downtime of T seconds:

   ``python live-failover.py scenario --sleep T``

* `stop` - spin down the cluster (and the automation agent)

   ``python live-failover.py stop``

These commands are meant to be used in sequence: ``start``, followed by one or more calls to ``scenario``, followed by ``stop``.

``live-failover.py`` creates a temporary file, called ``tmp_scenario_state.json``, during the ``start`` command.  If this file is not present, neither the ``scenario`` nor ``stop`` commands can be run.  This temporary file will be cleaned up during the ``stop`` command.

All commands can take ``--agent-config`` and ``--agent-log`` options, which set the location of files to be used by the automation agent. If either of these options is passed into the ``start`` command, the same options must also be passed into the ``scenario`` and ``stop`` commands on that run.  By default, ``--agent-config`` is ``agent-config.json`` and ``--agent-log`` is ``agent-log.json``.

All commands can take a ``--tombstone-file <filename>`` argument.  If this argument is passed in, ``live-failover.py`` will create a file with the specified filename just before exiting.  This option is intended for drivers that cannot use pid monitoring to understand when the script has exited. If the specified file already exists when ``live-failover.py`` runs, the script will write over that file.  Drivers should remove any file with the specified name before running ``live-failover.py``, since having a tombstone file that already exists is quite pointless.

Use `--help` for more information about ``live-failover.py`` and its usage.
