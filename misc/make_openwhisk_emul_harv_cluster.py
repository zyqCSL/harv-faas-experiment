# python3 make_openwhisk_cluster.py --cluster-config test_openwhisk.json --ctrl 2 --inv 2
import sys
import os
import argparse
import logging
from pathlib import Path
import json
import math
# from socket import SOCK_STREAM, socket, AF_INET, SOL_SOCKET, SO_REUSEADDR

from pathlib import Path
sys.path.append(str(Path.cwd()))

# -----------------------------------------------------------------------
# parser args definition
# -----------------------------------------------------------------------
parser = argparse.ArgumentParser()
# parser.add_argument('--cpus', dest='cpus', type=int, required=True)
# parser.add_argument('--stack-name', dest='stack_name', type=str, required=True)
parser.add_argument('--cluster-config', dest='cluster_config', type=str, required=True)
parser.add_argument('--ctrl', dest='num_controllers', type=int, required=True)
# parser.add_argument('--ctrl-vms', dest='num_controller_vms', type=int, required=True)
parser.add_argument('--inv', dest='num_invokers', type=int, required=True)
# data collection parameters
# TODO: add argument parsing here

# -----------------------------------------------------------------------
# parse args
# -----------------------------------------------------------------------
args = parser.parse_args()
num_controllers = args.num_controllers
# num_controller_vms = args.num_controller_vms
num_invokers = args.num_invokers
# assert num_controllers % num_controller_vms == 0
total_nodes = num_invokers + 1    # 1 for host
#------------- vm config --------------#
cluster_config_path = Path.cwd() / '..' / 'config' / 'templates' / args.cluster_config.strip()
node_config = {}
# host
node_config['node-0'] = {}
node_config['node-0']['size'] = 'Standard_D48s_v3'
node_id = 1
while node_id < total_nodes:
    node_name = 'node-'+str(node_id)
    assert node_name not in node_config
    node_id += 1
    node_config[node_name] = {}
    # node_config[node_name]['cpus'] = service_config[service]['node_cpus']
    node_config[node_name]['size'] = 'Standard_D32s_v3'

cluster_config = {}
cluster_config['nodes'] = node_config
cluster_config['host_node'] = 'node-0'

#------------- openwhisk role config --------------#
openwhisk_controllers = {}
openwhisk_invokers = {}
node_id = 1

invoker_vms = []
while len(invoker_vms) < num_invokers:
    invoker_vms.append('node-' + str(node_id))
    node_id += 1

for i in range(0, num_controllers):
    openwhisk_controllers['controller' + str(i)] = cluster_config['host_node']

for i in range(0, num_invokers):
    openwhisk_invokers['invoker' + str(i)] = invoker_vms[i]

cluster_config['openwhisk_roles'] = {} 
cluster_config['openwhisk_roles']['controllers'] = openwhisk_controllers
cluster_config['openwhisk_roles']['invokers'] = openwhisk_invokers

with open(str(cluster_config_path), 'w+') as f:
	json.dump(cluster_config, f, indent=4, sort_keys=True)