import argparse
import json
import logging
import math
import subprocess
import sys
import os
import threading
import time
import random
from pathlib import Path

sys.path.append(str(Path.cwd() / 'src'))
import openwhisk_config_gen
from util_func import scp
from util_func import ssh

def create_azure_resource_group(resource_group, 
                                location, quiet = False):
    _stdout = sys.stdout
    _stderr = sys.stderr
    if quiet:
        _stdout = subprocess.DEVNULL
        _stderr = subprocess.DEVNULL
    # az group create --name harvest-openwhisk --location westus2
    cmd = 'az group create' + \
        ' --name ' + resource_group + \
        ' --location ' + location
    subprocess.run(cmd, shell=True, stdout=_stdout, stderr=_stderr)

def delete_azure_resource_group(resource_group, quiet=False):
    _stdout = sys.stdout
    _stderr = sys.stderr
    if quiet:
        _stdout = subprocess.DEVNULL
        _stderr = subprocess.DEVNULL
    # az group delete -n harvest-openwhisk -y
    cmd = 'az group delete' + \
        ' --name ' + resource_group + \
        ' -y'
    subprocess.run(cmd, shell=True, stdout=_stdout, stderr=_stderr)

def open_azure_vm_port(resource_group, instance_name, port, quiet=False):
    _stdout = sys.stdout
    _stderr = sys.stderr
    if quiet:
        _stdout = subprocess.DEVNULL
        _stderr = subprocess.DEVNULL
    # az vm open-port --resource-group myResourceGroup --name myVM --port 80
    cmd = 'az vm open-port' + \
        ' --resource-group ' + resource_group + \
        ' --name ' + instance_name + \
        ' --port ' + port
    subprocess.run(cmd, shell=True, stdout=_stdout, stderr=_stderr)

def create_azure_vm(resource_group,
                    instance_name, username, 
                    public_key_path,
                    vm_size, disk_gb, 
                    location, startup_script_path, 
                    external_ips, internal_ips,
                    quiet=False):
    _stdout = sys.stdout
    _stderr = sys.stderr
    if quiet:
        _stdout = subprocess.DEVNULL
        _stderr = subprocess.DEVNULL
    '''
    az vm create --resource-group harvest-openwhisk --name test-1 
        --image UbuntuLTS --size Standard_D16s_v3 --data-disk-sizes-gb 20 
        --admin-username yanqi --location westus2
        --ssh-key-values
        --output json --verbose
    '''
    cmd = 'az vm create' + \
        ' --resource-group ' + resource_group + \
        ' --admin-username ' + username + \
        ' --name ' + instance_name + \
        ' --image UbuntuLTS' + \
        ' --size ' + vm_size + \
        ' --data-disk-sizes-gb ' + str(disk_gb) + \
        ' --location ' + location + \
        ' --ssh-key-values ' + str(public_key_path) + \
        ' --custom-data ' + str(startup_script_path) + \
        ' --output json' + \
        ' --verbose'

    az_log_json = subprocess.check_output(cmd, shell=True, stderr=_stderr)
    az_log = json.loads(az_log_json)
    if 'error' in az_log:
        logging.error('az vm create failed: ' + az_log)
    else:
        external_ip = az_log['publicIpAddress']
        external_ips[instance_name] = external_ip
        internal_ip = az_log['privateIpAddress']
        internal_ips[instance_name] = internal_ip

        # -----------------------------------------------------------------------
        # wait for startup script to finish
        # -----------------------------------------------------------------------
        logging.info('waiting for ' + instance_name + ' startup to finish')
        while True:
            try:
                res = subprocess.check_output('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' +
                                            '-i ' + str(rsa_private_key) + ' ' +
                                            username + '@' + external_ip +
                                            ' \'if [ -f /home/'+username +
                                            '/startup_finished ]; then echo yes; else echo no; fi\'',
                                            shell=True, stderr=_stderr).decode("utf-8").strip()
            except:
                logging.warning(instance_name + ' ssh error')
                res = ""

            if res == "yes":
                break
            time.sleep(30)

        logging.info("az vm create %s done" %instance_name)

        # -----------------------------------------------------------------------
        # scp generated private key to azure instance
        # -----------------------------------------------------------------------
        # logging.info('scp private key')
        scp(source='~/azure-serverless/keys/id_rsa',
            target=username+'@'+external_ip+':~/.ssh/id_rsa',
            identity_file=str(rsa_private_key), quiet=quiet)
        # -----------------------------------------------------------------------
        # set ssh files/directories privileges
        # -----------------------------------------------------------------------
        # logging.info('set .ssh files privileges')
        ssh(destination=username+'@'+external_ip,
            cmd='sudo chmod 700 ~/.ssh',
            identity_file=rsa_private_key, quiet=quiet)
        ssh(destination=username+'@'+external_ip,
            cmd='sudo chmod 600 ~/.ssh/id_rsa',
            identity_file=rsa_private_key, quiet=quiet)
        ssh(destination=username+'@'+external_ip,
            cmd='sudo chmod 600 ~/.ssh/authorized_keys',
            identity_file=rsa_private_key, quiet=quiet)
        ssh(destination=username+'@'+external_ip,
            cmd='sudo chown -R '+username+':'+username+' ~/.ssh',
            identity_file=rsa_private_key, quiet=quiet)

        # # make directory for openwhisk log
        # ssh(destination=username+'@'+external_ip,
        #     cmd='mkdir /home/' + username + '/openwhisk_locust_log',
        #     identity_file=rsa_private_key, quiet=quiet)
        
        open_azure_vm_port(resource_group, instance_name, "\'*\'")

        logging.info(instance_name + ' startup finished')


logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
# -----------------------------------------------------------------------
# miscs parameters
# -----------------------------------------------------------------------
location = 'westus2'
default_vm_size = 'Standard_D16s_v3'
invoker_vm_size = default_vm_size
startup_script_path = Path.home() / 'azure-serverless' / 'scripts' / 'startup.sh'

# -----------------------------------------------------------------------
# parser args definition
# -----------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument('--username', dest='username', type=str, default='yanqi')
parser.add_argument('--resource-group', dest='resource_group', type=str, default='harvest-openwhisk')
parser.add_argument('--init-group', dest='init_group', action='store_true')
parser.add_argument('--init-vms', dest='init_vms', action='store_true')
parser.add_argument('--background', dest='background', action='store_true')
# this should be a fixed number, and should be changed together with openwhisk implementation
# check the maxInvokerId in openwhisk CommonLoadBalancer.scala
parser.add_argument('--max-invoker-id', dest='max_invoker_id', type=int, default=499)
parser.add_argument('--real-harvest', dest='real_harvest', action='store_true')
parser.add_argument('--emul-harvest-trace', dest='emul_harvest_trace', type=str, default='')
parser.add_argument('--deploy-config', dest='deploy_config',
                    type=str, required=True)
parser.add_argument('--openwhisk-config', dest='openwhisk_config',
                    type=str, default='openwhisk')
parser.add_argument('--openwhisk-version', dest='openwhisk_version',
                    type=str, default='openwhisk-harv-vm-cgroup-azure-distributed-jsq')
parser.add_argument('--azure-deploy-openwhisk', dest='azure_deploy_openwhisk', action='store_true')

# -----------------------------------------------------------------------
# parse args
# -----------------------------------------------------------------------
args = parser.parse_args()
username = args.username
resource_group = args.resource_group
init_group = args.init_group
init_vms = args.init_vms
background = args.background
max_invoker_id = args.max_invoker_id
if(args.real_harvest):
    assert location == 'westus2'
    invoker_vm_size = 'Harvest_E2s_v3'
emul_harvest_trace = args.emul_harvest_trace

template_deploy_config_path = Path.cwd() / 'config' / 'templates' / args.deploy_config
deploy_config_path = template_deploy_config_path

openwhisk_config_dir = Path.cwd() / 'config' / args.openwhisk_config
harvest_trace_dir = Path.cwd() / 'harvest_vm_traces'
os.makedirs(str(openwhisk_config_dir), exist_ok=True)
openwhisk_version = args.openwhisk_version
azure_deploy_openwhisk = args.azure_deploy_openwhisk
wsk_api_host = '172.17.0.1'
wsk_auth = '23bc46b1-71f6-4ed5-8c54-816aa4f8c502:123zO3xZCLrMN6v2BKK1dXYFpXlPkccOFqm12CdAsMgRU4VrNZ9lyGVCGuMDGIwP'

# -----------------------------------------------------------------------
# ssh-keygen
# -----------------------------------------------------------------------
rsa_public_key = Path.home() / 'azure-serverless' / 'keys' / 'id_rsa.pub'
rsa_private_key = Path.home() / 'azure-serverless' / 'keys' / 'id_rsa'
if init_vms:
    logging.info('generate ssh keys')
    if rsa_private_key.exists():
        rsa_private_key.unlink()
    if rsa_public_key.exists():
        rsa_public_key.unlink()
    cmd = 'ssh-keygen -b 4096 -t rsa -f ' + str(Path.cwd() / 'keys' / 'id_rsa') + ' -q -N "" -C ' + username
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)

# -----------------------------------------------------------------------
# gcloud compute instances create
# -----------------------------------------------------------------------
# startup_script_path = Path.home() / 'azure-serverless' / 'scripts' / 'startup.sh'
public_key_path = Path.home() / 'azure-serverless' / 'keys' / 'id_rsa.pub'

external_ips = {}
internal_ips = {}
init_vm_threads = []
host_node = ''

if init_group:
    delete_azure_resource_group(resource_group=resource_group)
    create_azure_resource_group(resource_group=resource_group, location=location)

if init_vms:
    logging.info('starting init_vms')
    with open(str(deploy_config_path), 'r') as f:
        json_config = json.load(f)
        node_config = json_config['nodes']
        openwhisk_roles = json_config['openwhisk_roles']
        host_node = json_config['host_node']
        for node_name in node_config:
            disk_gb = 40
            vm_size = node_config[node_name]['size']          
            t = threading.Thread(target=create_azure_vm, kwargs={
                'resource_group': resource_group,
                'username': username,
                'instance_name': node_name,
                'location': location,
                'public_key_path': public_key_path,
                'vm_size': vm_size,
                'disk_gb': disk_gb,
                'startup_script_path': startup_script_path,
                'external_ips': external_ips,
                'internal_ips': internal_ips,
                'quiet': False
            })
            init_vm_threads.append(t)
            t.start()
            time.sleep(0.5)

    for t in init_vm_threads:
        t.join()
    logging.info('init_vms finished')

external_ip_path = Path.home() / 'azure-serverless' / 'logs' / 'external_ip.json'
internal_ip_path = Path.home() / 'azure-serverless' / 'logs' / 'internal_ip.json'
if init_vms:
    with open(str(external_ip_path), "w+") as f:
        json.dump(external_ips, f, indent=4, sort_keys=True)
    with open(str(internal_ip_path), "w+") as f:
        json.dump(internal_ips, f, indent=4, sort_keys=True)
else:
    with open(str(external_ip_path), 'r') as f:
        external_ips = json.load(f)
    with open(str(internal_ip_path), 'r') as f:
        internal_ips = json.load(f)

# create openwhisk config
controllers = {}
sorted_controllers = sorted(list(openwhisk_roles['controllers'].keys()), 
    key=lambda inv: int(inv.replace('controller', '')))
for ctrl in sorted_controllers:
    vm = openwhisk_roles['controllers'][ctrl]
    controllers[ctrl] = external_ips[vm]

invokers = {}
sorted_invokers = sorted(list(openwhisk_roles['invokers'].keys()), 
    key=lambda inv: int(inv.replace('invoker', '')))
for inv in sorted_invokers:
    vm = openwhisk_roles['invokers'][inv]
    invokers[inv] = external_ips[vm]

openwhisk_config_gen.generate_hosts(
    controller_vm_ips=controllers, 
    invoker_vm_ips=invokers, 
    host_ip=external_ips[host_node],
    config_dir=openwhisk_config_dir)

# the new_invoker_ids should be in the same order as 
# the new_invokers in hosts file
invoker_ids = [int(inv.replace('invoker', '')) for inv in sorted_invokers]
openwhisk_config_gen.generate_invoker_yml(
    config_dir=openwhisk_config_dir, 
    invoker_ids=invoker_ids)

openwhisk_config_gen.generate_couchdb_setup(
    config_dir=openwhisk_config_dir, 
    couchdb_ip=external_ips[host_node], 
    username=username)

openwhisk_config_gen.generate_setup_add_invoker(
    config_dir=openwhisk_config_dir, 
    couchdb_ip=external_ips[host_node], 
    username=username)

# todo: later should be scp directly to ansible directory on azure vm
clone_wsk_cmd = 'git clone https://github.com/zyqCSL/openwhisk_archive'
ssh(destination=username +'@' + external_ips[host_node],
    cmd=clone_wsk_cmd,
    identity_file=rsa_private_key)

azure_openwhisk_ansible_dir = '~/openwhisk_archive/' + openwhisk_version + '/ansible/'
azure_openwhisk_ansible_env_dir = azure_openwhisk_ansible_dir + 'environments/local/'

scp(source=openwhisk_config_dir / 'hosts.j2.ini', 
    target=username + '@' + external_ips[host_node] + ':' + azure_openwhisk_ansible_env_dir, 
    identity_file=str(rsa_private_key))

scp(source=openwhisk_config_dir / 'setup_couchdb.sh', 
    target=username + '@' + external_ips[host_node] + ':' + azure_openwhisk_ansible_dir, 
    identity_file=str(rsa_private_key))

if azure_deploy_openwhisk:
    azure_wsk_setup_cmd = 'cd ' + azure_openwhisk_ansible_dir + '; '
    azure_wsk_setup_cmd += './setup_couchdb.sh'
    ssh(destination=username +'@' + external_ips[host_node],
        cmd=azure_wsk_setup_cmd,
        identity_file=rsa_private_key)
    
    azure_wsk_deploy_cmd = 'cd ' + azure_openwhisk_ansible_dir + '; '
    azure_wsk_deploy_cmd += './deploy_couchdb.sh'
    ssh(destination=username +'@' + external_ips[host_node],
        cmd=azure_wsk_deploy_cmd,
        identity_file=rsa_private_key)
    
    # set up wsk
    azure_wsk_util_cp_cmd = 'sudo cp ~/openwhisk_archive/openwhisk-harv-vm-cgroup-azure-distributed/bin/wsk /usr/local/bin/'
    ssh(destination=username +'@' + external_ips[host_node],
        cmd=azure_wsk_util_cp_cmd,
        identity_file=rsa_private_key)
    
    # set api host & authentication
    azure_wsk_config_cmd = 'wsk property set --apihost ' + wsk_api_host + '; '
    azure_wsk_config_cmd += 'wsk property set --auth ' + wsk_auth
    ssh(destination=username +'@' + external_ips[host_node],
        cmd=azure_wsk_config_cmd,
        identity_file=rsa_private_key)
    
    # register benchmark functions
    azure_reg_func_cmd = 'cd ~/openwhisk_workloads; '
    azure_reg_func_cmd += 'python3 register_copy_actions.py'
    ssh(destination=username +'@' + external_ips[host_node],
        cmd=azure_reg_func_cmd,
        identity_file=rsa_private_key)

#------------------------- deploy minio --------------------------- #
# make minio config
minio_config = {}
minio_config['endpoint'] = external_ips[host_node] + ':9002'
minio_config['access_key'] = '5VCTEQOQ0GR0NV1T67GN'
minio_config['secret_key'] = '8MBK5aJTR330V1sohz4n1i7W5Wv/jzahARNHUzi3'
minio_config['bucket'] = 'openwhisk'
minio_config_path = openwhisk_config_dir / 'minio_config.json'
with open(str(minio_config_path), 'w+') as f:
    json.dump(minio_config, f, indent=4, sort_keys=True)

# scp minio config to remote workload directory on host
remote_minio_dir = '/home/' + username + '/openwhisk_workloads/minio/'
remote_locust_dir = '/home/' + username + '/openwhisk_workloads/openwhisk_locust/faas_data/'
scp(source=openwhisk_config_dir / 'minio_config.json', 
    target=username + '@' + external_ips[host_node] + ':' + remote_minio_dir, 
    identity_file=str(rsa_private_key))
scp(source=openwhisk_config_dir / 'minio_config.json', 
    target=username + '@' + external_ips[host_node] + ':' + remote_locust_dir, 
    identity_file=str(rsa_private_key))

# set up minio
minio_cmd = 'cd ' + remote_minio_dir + '; python3 setup_minio.py --minio-config minio_config.json'
ssh(destination=username +'@' + external_ips[host_node],
    cmd=minio_cmd,
    identity_file=rsa_private_key)

# -----------------------------------------------------------------------
# run exp
# -----------------------------------------------------------------------
azure_scripts_dir = Path.cwd() / 'azure_scripts'
# generate invoker_ips file & copy to host
with open(str(openwhisk_config_dir / 'invoker_ips.json'), 'w+') as f:
    json.dump(invokers, f, indent=4, sort_keys=True)
    
scp(source= openwhisk_config_dir / 'invoker_ips.json', 
    target=username + '@' + external_ips[host_node] + ':~/', 
    identity_file=str(rsa_private_key))

# copy monitor to invokers
for inv in invokers:
    scp(source= azure_scripts_dir / 'monitor_cpu.py', 
        target=username + '@' + invokers[inv] + ':~/', 
        identity_file=str(rsa_private_key))

# # copy exp script to host
# scp(source= azure_scripts_dir / 'run_locust.py', 
#     target=username + '@' + external_ips[host_node] + ':~/', 
#     identity_file=str(rsa_private_key))

scp(source= azure_scripts_dir / 'run_locust_loop.py', 
    target=username + '@' + external_ips[host_node] + ':~/', 
    identity_file=str(rsa_private_key))

scp(source= azure_scripts_dir / 'azure_read_function_stats.py', 
    target=username + '@' + external_ips[host_node] + ':~/', 
    identity_file=str(rsa_private_key))

# copy harvest vm emulators and trace to invokers
if emul_harvest_trace != '':
    trace_dir = harvest_trace_dir / emul_harvest_trace
    # make sure #invokers = #traces
    trace_list = [k for k in os.listdir(str(trace_dir)) if '.txt' in k]
    assert len(trace_list) == len(invokers)
    trace_pointer = 0
    used_traces = []
    for inv in invokers:
        # scp emulator
        scp(source= azure_scripts_dir / 'harvest_vm_emulator.py', 
            target=username + '@' + invokers[inv] + ':~/', 
            identity_file=str(rsa_private_key))    
        # scp trace
        assert trace_list[trace_pointer] not in used_traces
        used_traces.append(trace_list[trace_pointer])
        scp(source= trace_dir / trace_list[trace_pointer], 
            target=username + '@' + invokers[inv] + ':~/' + inv + '.txt', 
            identity_file=str(rsa_private_key))
        trace_pointer += 1