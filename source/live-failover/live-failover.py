#!/usr/bin/env python3

import argparse, json, os, signal, subprocess, sys, time, traceback

def parse_arguments():
    '''Parse the command-line arguments passed to the script and return the args object.'''
    parser = argparse.ArgumentParser(description='Live Failover Testing Script')
    subparsers = parser.add_subparsers(title='command', dest='command', help='sub-command help')
    
    start = subparsers.add_parser('start', 
        description='start the automation agent and initialize the cluster',
        help='start the automation agent and initialize the cluster')
    scenario = subparsers.add_parser('scenario',
        description='run the scenario on the already-started cluster',
        help='run the scenario on the already-started cluster')
    stop = subparsers.add_parser('stop',
        description='stop the automation agent',
        help='stop the automation agent')
    
    start.add_argument(
        'topology',
        help='the topology JSON file to use for the scenario')
        
    for p in [start, scenario, stop]:
        p.add_argument(
            '--agent-config',
            default='agent-config.json',
            help='location of the config file to be used by the automation agent')
            
    for p in [start, scenario, stop]:
        p.add_argument(
            '--agent-log',
            default='agent.log',
            help="location of the automation agent's log file")

    scenario.add_argument(
        '--sleep',
        type=int,
        default=3,
        help='duration (in seconds) to sleep between node restarts')
        
    for p in [start, scenario, stop]:
        p.add_argument(
            '--tombstone-file',
            help='create a tombstone file at the given path upon exit')

    for p in [start, scenario, stop]:
        p.add_argument(
            '--debug',
            action='store_true',
            help='print stack trace if an error occurs')
   
    # Print help and exit if a command is not specified.
    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(0)
    
    return parser.parse_args()

def load_json(filename):
    '''Reads a JSON file and returns the parsed data.'''
    with open(filename) as f:
        return json.load(f)

def write_json(data, filename):
    '''Writes JSON to the specified file on disk.'''
    with open(filename, 'w') as f:
        json.dump(data, f)
    
def goal_state_message(num_processes):
    '''Helper to construct the automation agent log
       string indicating that topology updates have 
       finished.'''
    return f"All {num_processes} Mongo processes are in goal state"
    
def update_agent_topology(topology, agent_config):
    '''Writes the topology to the agent config file,
       which will cause the automation agent to make
       any changes as necessary.'''
    write_json (topology, agent_config)

def wait_for_agent_goal_state(agent_log, num_processes, msg, start_from=0):
    '''Wait for the automation agent to reach the goal
       state.'''

    goal_state = goal_state_message(num_processes)
    config_err_msg = "Error reading cluster config"
    duplicate_agent_msg = "Is there another automation agent"
    curr_loc = start_from

    print(f"{msg}...")

    while True:        
        with open(agent_log) as log_file:
            log_file.seek(curr_loc)

            new_content = log_file.read()
            curr_loc = log_file.tell()
            
            if goal_state in new_content:
                break

            if duplicate_agent_msg in new_content:
                print ("Error: cannot start agent. "
                       "Is the automation agent already running?", file=sys.stderr)
                return -1

            if config_err_msg in new_content:
                print ("Error: could not load cluster config. "
                       "Examine agent.log for more information.", file=sys.stderr)
                return -1
            
        time.sleep(2)

    return curr_loc

def load_state_file (agent_log, agent_config):
    '''Reads stored script data from a file on disk.
       Returns the agent pid.'''
    data = load_json ("tmp_scenario_state.json")
    if agent_log != data["agent_log"]:
        raise Exception("must use consistent agent logfile")
    if agent_config != data["agent_config"]:
        raise Exception("must use consistent agent config")

    return data["agent_pid"], data["initial_topology"]

def save_state_to_file (topology, agent_log, agent_config, agent_pid):
    '''Writes necessary state to a temporary file on disk.'''
    data = {
        "agent_log" : agent_log,
        "agent_config" : agent_config,
        "agent_pid" : agent_pid,
        "initial_topology": topology,
        }
    write_json (data, "tmp_scenario_state.json")

def cleanup_state_file ():
    '''Remove temporary state file.'''
    if os.path.exists ("tmp_scenario_state.json"):
        os.remove("tmp_scenario_state.json")
    
def start_automation_agent(agent_config, agent_log, topology):
    '''Initialize the automation agent and wait for
       the initial topology to be ready.
       
       Returns the automation agent PID.'''
       
    print('Launching the automation agent...')
    sys.stdout.flush()

    # Remove agent files if they exist already
    if os.path.exists (agent_log):
        os.remove(agent_log)
    if os.path.exists (agent_config):
        os.remove(agent_config)
    
    update_agent_topology(topology, agent_config)

    # TODO: starting the agent with Popen blocks all
    # printed output until the agent exits, fix this.
    with open(agent_log, 'a') as log_file:
        pid = subprocess.Popen(
                    ['./mongodb-mms-automation-agent', '-cluster', agent_config], 
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    bufsize=0,
                    universal_newlines=True).pid

    print('Waiting for agent to reach goal state...')

    wait_for_agent_goal_state(
        agent_log, 
        len(topology['processes']), 
        'Waiting for cluster to come online...')
    
    return pid    

def restart_node(sleep, agent_config, agent_log, topology, i):
    '''Performs a restart on node i in the cluster by
       writing to the automation config to disable the
       node. This function will sleep for the given duration
       after disabling the node before re-enabling it.

       When this function returns, the node will have been
       fully restarted, so the topology is back to the same
       state it was in when the function was called.'''
    process = topology['processes'][i]
    print (f"Shutting down node {process['name']}")
    process['disabled'] = True
    
    read_from = os.path.getsize(agent_log)
    update_agent_topology(topology, agent_config)
    wait_for_agent_goal_state(
        agent_log, 
        len(topology['processes']), 
        f"shutting down node #{i}...", 
        read_from)

    print ("Waiting...")
    time.sleep(sleep) 

    print (f"Starting up node {process['name']}")
    del process['disabled']
    read_from = os.path.getsize(agent_log)
    update_agent_topology(topology, agent_config)
    wait_for_agent_goal_state(
        agent_log,
        len(topology['processes']),
        f"starting up node #{i}...",
        read_from)
        
    
def restart_each_node(sleep, agent_config, agent_log, topology):
    '''Restarts each node in the cluster individually
       (with sleeps for the given duration interleaved).'''
    # TODO: this doesn't take node ordering into consideration
    # for example, we should probably do the secondaries first,
    # then the primary, to mimic Atlas maintenance.
    for i in range(len(topology['processes'])):
        restart_node(sleep, agent_config, agent_log, topology, i)
    
def kill_and_wait(pid):
    '''Kills the subprocess with the given pid and waits
       for it to terminate.'''
    try:
        os.kill(pid, signal.SIGINT)
    
        while True:
            finished_pid, _ = os.wait()
        
            if finished_pid == pid:
                return
            
            time.sleep(2)
    except Exception as e:
        return

def create_tombstone(tombstone_file, msg):    
    with open(tombstone_file, 'w') as f:
        f.write(msg)

def cleanup_agent(agent_pid, agent_log, agent_config):
    print('Killing the automation agent.')
    kill_and_wait(agent_pid)

    # It is helpful to examine the log file on failure
    #os.remove(agent_log)
    os.remove(agent_config)


def finish(agent_pid, agent_config, agent_log, topology, tombstone_file):
    '''Perform final cleanup steps and create the tombstone file if necessary.'''
    
    print('Scenario complete.')
    
    for process in topology['processes']:
        process['disabled'] = True
    
    read_from = os.path.getsize(agent_log)
    update_agent_topology(topology, agent_config) 
    wait_for_agent_goal_state(
        agent_log,
        len(topology['processes']),
        'Waiting for cluster to shut down...',
        read_from)

    cleanup_agent (agent_pid, agent_log, agent_config)
    if tombstone_file:
        create_tombstone (tombstone_file, "Scenario completed")

def read_topology(topology):
    # TODO: consider something clever here to set
    # the config build info based on the os
    print ("Reading topology...")
    return load_json(topology);
    
def main():
    '''Launches the following script commands:

       start - Start up the automation agent, and then
       use it to spin up the cluster specified by
       args.topology.

       scenario - Use the automation agent to put
       the cluster specified by args.topology through a
       rolling restart with a downtime of args.sleep.

       stop - Use the automation agent to stop the
       cluster specified by args.topology, then stop
       the automation agent.'''
    try:
        args = parse_arguments()
        
        agent_pid = -1

        print (f"Running command '{args.command}'")

        if args.command == "start":
            print (f"Starting cluster for config {args.topology}...")
            topology = read_topology(args.topology)
            agent_pid = start_automation_agent (
                args.agent_config,
                args.agent_log,
                topology)

            if agent_pid < 0:
                raise Exception("Could not start agent");
            save_state_to_file (args.topology,
                                args.agent_log,
                                args.agent_config,
                                agent_pid)

        elif args.command == "scenario":
            print (f"Running scenario for config {args.agent_config} with downtime {args.sleep} seconds")
                   
            try:
                agent_pid, topology_file = load_state_file (args.agent_log,
                                                            args.agent_config)
            except FileNotFoundError:
               raise Exception('unable to run scenario; agent is not running') 

            topology = read_topology(topology_file)            
            restart_each_node(
                args.sleep, 
                args.agent_config, 
                args.agent_log, 
                topology)
            save_state_to_file (topology_file,
                                args.agent_log,
                                args.agent_config,
                                agent_pid)

        elif args.command == "stop":
            print (f"Shutting down cluster for config {args.agent_config}")
            try:
                agent_pid, topology_file = load_state_file (args.agent_log,
                                                            args.agent_config)
            except FileNotFoundError:
               raise Exception('unable to shut down cluster; agent is not running') 
               
            topology = read_topology(topology_file)
            finish(agent_pid,
                   args.agent_config,
                   args.agent_log,
                   topology,
                   args.tombstone_file)
            cleanup_state_file ()

        else:
            raise Exception("Unrecognized state")

        print (f"'{args.command}' command complete.")

    except Exception as e:
        print ("Encountered an exception")
        print (f"    {e}")
       
        if args.debug:
            traceback.print_exc()
       
        if agent_pid > 0:
            cleanup_agent (agent_pid, args.agent_log, args.agent_config)
        if args.tombstone_file:
            create_tombstone (args.tombstone_file, "Exception")

        sys.exit(1)

    if args.tombstone_file:
        create_tombstone (args.tombstone_file, "Command complete")

    sys.exit(0);
        
main()
