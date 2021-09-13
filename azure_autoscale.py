import argparse
import json
import logging
import math
import subprocess
import sys
import os
import threading
import time
import requests
import random
import copy
from pathlib import Path

sys.path.append(str(Path.cwd() / 'src'))
import openwhisk_config_gen
from util_func import scp
from util_func import ssh, ssh_checkoutput

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

def get_azure_subscription_id(name, quiet=False):
    _stderr = sys.stderr
    if quiet:
        _stderr = subprocess.DEVNULL
    cmd = 'az account subscription list'
    out = subprocess.check_output(cmd, shell=True, stderr=_stderr)
    subscriptions = json.loads(out)
    for subs in subscriptions:
        if subs['displayName'] == name:
            return subs['subscriptionId']
    return ''

def get_azure_vm_list(resource_group, quiet=False):
    _stderr = sys.stderr
    if quiet:
        _stderr = subprocess.DEVNULL
    cmd = 'az vm list -g ' + resource_group + ' -d'
    out = subprocess.check_output(cmd, shell=True, stderr=_stderr)
    vm_info_list = json.loads(out)
    alive_vms = []
    for vm_info in vm_info_list:
        if vm_info['powerState'] == 'VM running' or vm_info['powerState'] == '':
            vm_name = vm_info['name']
            alive_vms.append(vm_name)
        else:
            logging.info('vm: %s in abnormal state: %s' %(
                vm_info['name'], vm_info['powerState']))
    return alive_vms

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

def simulate_azure_vm_eviction(resource_group, vm_name, quiet=False):
    _stdout = sys.stdout
    _stderr = sys.stderr
    if quiet:
        _stdout = subprocess.DEVNULL
        _stderr = subprocess.DEVNULL

    cmd = 'az vm simulate-eviction' + \
        ' --resource-group ' + resource_group + \
        ' --name ' + vm_name  
    logging.info('sim evict cmd = %s' %cmd)
    subprocess.run(cmd, shell=True, stdout=_stdout, stderr=_stderr)

def create_azure_vm(resource_group,
                    instance_name, username, 
                    public_key_path,
                    vm_size, disk_gb, 
                    location, startup_script_path, 
                    external_ips, internal_ips,
                    evictable, vm_created,
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
    if evictable:
        # default policy is Deallocate (can be set to Delete)
        cmd = 'az vm create' + \
            ' --resource-group ' + resource_group + \
            ' --admin-username ' + username + \
            ' --name ' + instance_name + \
            ' --image UbuntuLTS' + \
            ' --size ' + vm_size + \
            ' --location ' + location + \
            ' --priority Spot' + \
            ' --max-price -1' + \
            ' --eviction-policy Delete' + \
            ' --ssh-key-values ' + str(public_key_path) + \
            ' --custom-data ' + str(startup_script_path) + \
            ' --output json' + \
            ' --verbose'
    else:
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

    try:
        az_log_json = subprocess.check_output(cmd, shell=True, stderr=_stderr)
    except subprocess.CalledProcessError as e:
        logging.error(e.output)
        vm_created[instance_name] = False
        return
    az_log = json.loads(az_log_json)
    if 'error' in az_log:
        logging.error('az vm create failed: ' + az_log)
        assert instance_name not in vm_created
        vm_created[instance_name] = False
        return
    else:
        external_ip = az_log['publicIpAddress']
        external_ips[instance_name] = external_ip
        internal_ip = az_log['privateIpAddress']
        internal_ips[instance_name] = internal_ip

        # -----------------------------------------------------------------------
        # wait for startup script to finish
        # -----------------------------------------------------------------------
        logging.info('waiting for ' + instance_name + ' startup to finish')
        left_trials = 3
        ssh_success = False
        while True:
            try:
                res = subprocess.check_output('ssh -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 -o StrictHostKeyChecking=no ' +
                                            '-i ' + str(rsa_private_key) + ' ' +
                                            username + '@' + external_ip +
                                            ' \'if [ -f /home/'+username +
                                            '/startup_finished ]; then echo yes; else echo no; fi\'',
                                            shell=True, stderr=_stderr).decode("utf-8").strip()
            except:
                left_trials -= 1
                logging.warning('%s ssh error, %d trials left' %(
                    instance_name, left_trials))
                res = ""
                if left_trials <= 0:
                    break

            if res == "yes":
                ssh_success = True
                break
            time.sleep(10)

        if ssh_success:
            logging.info("az vm create %s done" %instance_name)
        else:
            logging.error("az vm create %s ssh failed" %instance_name)
            assert instance_name not in vm_created
            vm_created[instance_name] = False
            return

        # -----------------------------------------------------------------------
        # scp generated private key to azure instance
        # -----------------------------------------------------------------------
        # logging.info('scp private key')
        scp(source= str(Path.cwd()) + '/keys/id_rsa',
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
        
        assert instance_name not in vm_created
        vm_created[instance_name] = True
        logging.info(instance_name + ' startup finished')


logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
# -----------------------------------------------------------------------
# miscs parameters
# -----------------------------------------------------------------------
location = 'westus2'
default_vm_size = 'Standard_D16s_v3'
invoker_vm_size = default_vm_size
startup_script_path = Path.cwd() / 'scripts' / 'startup.sh'
harvest_startup_script_path = Path.cwd() / 'scripts' / 'startup_harvest.sh'

# -----------------------------------------------------------------------
# parser args definition
# -----------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument('--username', dest='username', type=str, default='yanqi')
parser.add_argument('--subscription', dest='subscription', type=str, default='Serverless OpenWhisk')
parser.add_argument('--resource-group', dest='resource_group', type=str, default='harvest-serverless')
parser.add_argument('--background', dest='background', action='store_true')
# if invoker ids should be reshuffed (should be set true when using consistent hashing)
parser.add_argument('--shuffle-invoker-ids', dest='shuffle_invoker_ids', action='store_true')
parser.add_argument('--evict-invoker', dest='evictable_invoker', action='store_true')
# this should be a fixed number, and should be changed together with openwhisk implementation
# check the maxInvokerId in openwhisk CommonLoadBalancer.scala
parser.add_argument('--max-invoker-id', dest='max_invoker_id', type=int, default=499)
# azure config: servers & their roles in openwhisk
parser.add_argument('--deploy-config', dest='deploy_config',
                    type=str, required=True)
# dir to save openwhisk internal deployment scripts
parser.add_argument('--openwhisk-config', dest='openwhisk_config',
                    type=str, default='openwhisk')
parser.add_argument('--openwhisk-version', dest='openwhisk_version',
                    type=str, default='openwhisk-harv-vm-cgroup-azure-distributed')

#------ eviction simulation ------#
parser.add_argument('--exp-time', dest='exp_time', type=int, required=True)
parser.add_argument('--req-cluster-vcpus', dest='req_cluster_vcpus', type=int, required=True)
parser.add_argument('--est-harv-vm-vcpus', dest='est_harv_vm_vcpus', type=int, default=6)
parser.add_argument('--check-interval', dest='check_interval', type=int, default=30)

# -----------------------------------------------------------------------
# parse args
# -----------------------------------------------------------------------
args = parser.parse_args()
username = args.username
subscription = args.subscription
# subscription_id = get_azure_subscription_id(subscription)
# assert subscription_id != ''
# logging.info('subscription_id = %s' %subscription_id)
resource_group = args.resource_group
background = args.background
shuffle_invoker_ids = args.shuffle_invoker_ids
evictable_invoker = args.evictable_invoker
max_invoker_id = args.max_invoker_id

#------- vm failure related --------#
exp_time = args.exp_time
check_interval = args.check_interval
req_cluster_vcpus = args.req_cluster_vcpus
est_harv_vm_vcpus = args.est_harv_vm_vcpus
default_harv_vm_size = 'Harvest_E2s_v3'

def generate_new_invoker_id(invoker_ids, max_invoker_id, req_invoker_num):
    all_invoker_ids = list(range(0, max_invoker_id + 1))
    for inv_id in invoker_ids:
        all_invoker_ids.remove(inv_id)
    new_invoker_ids = random.sample(all_invoker_ids, req_invoker_num)
    return new_invoker_ids

# -----------------------------------------------------------------------
# ssh-key
# -----------------------------------------------------------------------
rsa_public_key = Path.cwd() / 'keys' / 'id_rsa.pub'
rsa_private_key = Path.cwd() / 'keys' / 'id_rsa'

# -----------------------------------------------------------------------
# azure vm config
# -----------------------------------------------------------------------
deploy_config = {}
if shuffle_invoker_ids:
    # invoker_ids already shuffled, should have been saved under config directly
    deploy_config_path = Path.cwd() / 'config' / args.deploy_config
    with open(str(deploy_config_path), 'r') as f:
        deploy_config = json.load(f)
else:
    # invoker_ids not shuffled, read from template dir
    # and generate a new one for dynamic update
    template_deploy_config_path = Path.cwd() / 'config' / 'templates' / args.deploy_config
    deploy_config_path = Path.cwd() / 'config' / args.deploy_config
    with open(str(template_deploy_config_path), 'r') as f:
        deploy_config = json.load(f)
    with open(str(deploy_config_path), 'w+') as f:
        json.dump(deploy_config, f, indent=4, sort_keys=True)

openwhisk_roles_config = deploy_config['openwhisk_roles']
init_num_invokers = len(openwhisk_roles_config['invokers'])
nodes_config = deploy_config['nodes']
vm_id_base = 0  # the next id to create a vm
for inv_name in openwhisk_roles_config['invokers']:
    inv_node = openwhisk_roles_config['invokers'][inv_name]
    assert inv_node in nodes_config
    nodes_config[inv_node]['role'] = inv_name
for ctrl_name in openwhisk_roles_config['controllers']:
    ctrl_node = openwhisk_roles_config['controllers'][ctrl_name]
    assert ctrl_node in nodes_config
    nodes_config[ctrl_node]['role'] = 'controller'
host_node = deploy_config['host_node']
for vm in nodes_config:
    vm_id = int(vm.split('-')[-1])
    if vm_id + 1 > vm_id_base:
        vm_id_base = vm_id + 1

external_ip_path = Path.cwd() / 'logs' / 'external_ip.json'
internal_ip_path = Path.cwd() / 'logs' / 'internal_ip.json'
with open(str(external_ip_path), 'r') as f:
    external_ips = json.load(f)
with open(str(internal_ip_path), 'r') as f:
    internal_ips = json.load(f)
azure_scripts_dir = Path.cwd() / 'azure_scripts'

# -----------------------------------------------------------------------
# openwhisk config
# -----------------------------------------------------------------------
openwhisk_config_dir = Path.cwd() / 'config' / args.openwhisk_config
os.makedirs(str(openwhisk_config_dir), exist_ok=True)
openwhisk_version = args.openwhisk_version
wsk_api_host = '172.17.0.1'
wsk_auth = '23bc46b1-71f6-4ed5-8c54-816aa4f8c502:123zO3xZCLrMN6v2BKK1dXYFpXlPkccOFqm12CdAsMgRU4VrNZ9lyGVCGuMDGIwP'

# azure openwhisk deployment config path (on azure host node)
azure_openwhisk_path =  '~/openwhisk_archive/' + openwhisk_version + '/'
azure_openwhisk_ansible_dir = azure_openwhisk_path + 'ansible/'
azure_openwhisk_ansible_env_dir = azure_openwhisk_ansible_dir + 'environments/local/'

# -----------------------------------------------------------------------
# check vm rsc & redeploy
# -----------------------------------------------------------------------
# monitors the number of healthy invokers
# and make sure #invokers are constant by recreating invokers to replace evicted ones
def get_vm_vcpu(username, vm_name, vm_ip, identity_file, vm_vcpus, quiet=False, timeout=None):
    cmd = 'docker ps | grep invoker'
    if timeout == None:
        r = ssh_checkoutput(destination=username+'@'+vm_ip, 
            cmd=cmd, identity_file=str(identity_file), quiet=quiet)
    else:
        left_trials = 3
        while left_trials > 0:
            r = ssh_checkoutput(destination=username+'@'+vm_ip, 
                cmd=cmd, identity_file=str(identity_file), quiet=quiet, timeout=timeout)
            if r != None:
                break
            left_trials -= 1
            time.sleep(5)
    
    # consider the vm dead if invoker is not deployed
    if r == None:
        logging.warning('%s has no invoker deployed' %vm_name)
        return

    cmd = 'cat /var/lib/hyperv/.kvp_pool_0'
    if timeout == None:
        r = ssh_checkoutput(destination=username+'@'+vm_ip, 
            cmd=cmd, identity_file=str(identity_file), quiet=quiet)
    else:
        left_trials = 3
        while left_trials > 0:
            r = ssh_checkoutput(destination=username+'@'+vm_ip, 
                cmd=cmd, identity_file=str(identity_file), quiet=quiet, timeout=timeout)
            if r != None:
                break
            left_trials -= 1
            time.sleep(5)
    if r != None:
        r = r.decode("utf-8")
        # print(r)
        r = [k for k in r.split("\u0000") if k != '']
        vm_vcpus[vm_name] = float(r[-1])

def check_cluster_vcpu(external_ips, invoker_config, username, identity_file):
    vm_vcpus = {}
    threads = []
    for inv in invoker_config:
        vm_name = invoker_config[inv]
        vm_ip = external_ips[vm_name]
        t = threading.Thread(target=get_vm_vcpu, kwargs={
                'username': username,
                'vm_name': vm_name,
                'vm_ip': vm_ip,
                'identity_file': identity_file,
                'vm_vcpus': vm_vcpus,
                'quiet': False,
                'timeout': 10
            })
        t.start()
        time.sleep(0.1)
        threads.append(t)
    for t in threads:
        t.join()
    info = ''
    sum_vcpus = 0
    for vm in vm_vcpus:
        if info != '':
            info += ', '
        info += vm + ': ' + str(vm_vcpus[vm])
        sum_vcpus += vm_vcpus[vm]
    logging.info('vm detailed vcpus: %s' %info)
    logging.info('cluster sum vcpus = %d' %sum_vcpus)
    return sum_vcpus, vm_vcpus

# main loop
operation_log = {}
init_check = True
start_time = time.time()
prev_check_time = start_time
while time.time() - start_time <= exp_time:
    cur_time = time.time()
    if cur_time - prev_check_time < check_interval:
        time.sleep(check_interval - (cur_time - prev_check_time))
    else:
        prev_check_time = time.time()

        update_config = False
        invoker_config = copy.copy(openwhisk_roles_config['invokers'])

        op_time = time.time() - start_time
        operation_log[op_time] = {}

        cluster_vcpus, live_vm_vcpus = check_cluster_vcpu(external_ips=external_ips, 
            invoker_config=invoker_config, 
            username=username, identity_file=rsa_private_key)
        operation_log[op_time]['cluster_vcpus'] = cluster_vcpus

        failed_vms = {}
        live_vm_list = list(live_vm_vcpus.keys())
        dead_invokers = {}  # indexed by invoker
        alive_invokers = {}

        for inv in invoker_config:
            inv_vm = invoker_config[inv]
            if inv_vm in live_vm_vcpus:
                assert inv not in alive_invokers
                alive_invokers[inv] = inv_vm
            else:
                assert inv not in dead_invokers
                assert inv_vm not in failed_vms
                dead_invokers[inv] = inv_vm
                failed_vms[inv_vm] = nodes_config[inv_vm] # contain size & role info
                update_config = True
                logging.info('Failed vm = %s, failed invoker = %s, at time %.1f' %(
                    inv_vm, inv, time.time() - start_time))
                
        operation_log[op_time]['alive_invokers'] = copy.copy(alive_invokers)
        operation_log[op_time]['alive_vms'] = copy.copy(live_vm_list)

        # if len(alive_invokers) == init_num_invokers:
        #     logging.info('No invoker failure detected at time = %.1f' %(time.time() - start_time))
        #     # continue
        # else:
        #     update_config = True
        logging.info('At time = %.1f,live_vms=%s' %(
            time.time() - start_time,
            ', '.join(live_vm_list) ))
        
        operation_log[op_time]['failed_invokers'] = copy.copy(dead_invokers)
        operation_log[op_time]['failed_vms'] = copy.copy(failed_vms)

        # remove dead vms from data structures
        for vm in failed_vms:
            if vm in external_ips:
                del external_ips[vm]
            if vm in internal_ips:
                del internal_ips[vm]
            if vm in nodes_config:
                del nodes_config[vm]
        
        if req_cluster_vcpus > cluster_vcpus:
            update = True
            req_invoker_num = int(math.ceil((req_cluster_vcpus - cluster_vcpus)/est_harv_vm_vcpus))
            logging.info('%f vcpus aka. %d invokers needed' %(req_cluster_vcpus-cluster_vcpus, req_invoker_num))
            assert req_invoker_num > 0

            # generate new invoker ids
            alive_invoker_ids = []
            for inv in alive_invokers:
                inv_id = int(inv.replace('invoker', ''))
                alive_invoker_ids.append(inv_id)
            new_invoker_ids = generate_new_invoker_id(invoker_ids=alive_invoker_ids, 
                max_invoker_id=max_invoker_id, 
                req_invoker_num=req_invoker_num)

            # create new vms
            vm_create_start_time = time.time()
            init_vm_threads = {}
            new_vms = {}
            new_invokers = {}
            vm_created_flags = {}
            logging.info('#--------------- starting to create new vms ---------------#')
            index = 0
                    
            for i in range(0, req_invoker_num):
                disk_gb = 40
                evictable = False
                vm_size = default_harv_vm_size
                vm_startup_script_path = startup_script_path
                if 'Harvest' in vm_size:
                    evictable = evictable_invoker
                    vm_startup_script_path = harvest_startup_script_path
                vm_name = 'node-' + str(vm_id_base)
                invoker = 'invoker' + str(new_invoker_ids[index])
                vm_id_base += 1
                index += 1
                new_vms[vm_name] = {}
                new_vms[vm_name]['size'] = vm_size
                new_vms[vm_name]['role'] = invoker
                new_invokers[invoker] = vm_name
                logging.info('creating vm %s for invoker %s' %(vm_name, invoker))                   
                t = threading.Thread(target=create_azure_vm, kwargs={
                    'resource_group': resource_group,
                    'username': username,
                    'instance_name': vm_name,
                    'location': location,
                    'public_key_path': rsa_public_key,
                    'vm_size': vm_size,
                    'disk_gb': disk_gb,
                    'startup_script_path': vm_startup_script_path,
                    'external_ips': external_ips,
                    'internal_ips': internal_ips,
                    'evictable': evictable,
                    'vm_created': vm_created_flags,
                    'quiet': False
                })
                init_vm_threads[vm_name] = t
                t.start()
                time.sleep(0.1)

            for vm in init_vm_threads:
                logging.info('waiting for %s creation to complete' %vm)
                init_vm_threads[vm].join()
                logging.info('%s creation completed' %vm)

            planned_vms = list(new_vms.keys())    
            for vm in planned_vms:
                if vm not in vm_created_flags or not vm_created_flags[vm]:
                    # vm creation failed, delete metadata of this vm
                    if vm in external_ips:
                        del external_ips[vm]
                    if vm in internal_ips:
                        del internal_ips[vm]
                    inv = ''
                    if vm in new_vms:
                        inv = new_vms[vm]['role']
                        del new_vms[vm]
                    if inv in new_invokers:
                        del new_invokers[inv]
            
            vm_create_end_time = time.time()
            logging.info('#--------------- creating new vms finished ---------------#')

            updated_invoker_roles = {}
            # include existing invokers
            for invoker in alive_invokers:
                updated_invoker_roles[invoker] = alive_invokers[invoker]
            # update with new vms & invokers
            for vm in new_vms:
                nodes_config[vm] = new_vms[vm]
                invoker = new_vms[vm]['role']
                updated_invoker_roles[invoker] = vm
            for inv in new_invokers:
                assert inv in updated_invoker_roles
            deploy_config['nodes'] = nodes_config
            openwhisk_roles_config['invokers'] = updated_invoker_roles
            deploy_config['openwhisk_roles'] = openwhisk_roles_config
            with open(str(deploy_config_path), 'w+') as f:
                json.dump(deploy_config, f,  indent=4, sort_keys=True)
            #--- ips ---#
            with open(str(external_ip_path), "w+") as f:
                json.dump(external_ips, f, indent=4, sort_keys=True)
            with open(str(internal_ip_path), "w+") as f:
                json.dump(internal_ips, f, indent=4, sort_keys=True)

            # -----------------------------------------------------------------------
            # deploy new invokers on new vms
            # -----------------------------------------------------------------------
            #------ create openwhisk config ----------#
            # invoker ips
            sorted_exist_invokers = sorted(list(alive_invokers.keys()), 
                key=lambda inv: int(inv.replace('invoker', '')))
            sorted_new_invokers = sorted(list(new_invokers.keys()), 
                key=lambda inv: int(inv.replace('invoker', '')))
            exist_invoker_vm_ips = {}     
            new_invoker_vm_ips = {}
            for inv in sorted_exist_invokers:
                vm = alive_invokers[inv]
                exist_invoker_vm_ips[inv] = external_ips[vm]
            for inv in sorted_new_invokers:
                vm = new_invokers[inv]
                new_invoker_vm_ips[inv] = external_ips[vm]
            # controller ips
            controller_vm_ips = {}
            sorted_controllers = sorted(list(openwhisk_roles_config['controllers'].keys()), 
                key=lambda inv: int(inv.replace('controller', '')))
            for ctrl in sorted_controllers:
                vm = openwhisk_roles_config['controllers'][ctrl]
                controller_vm_ips[ctrl] = external_ips[vm]

            # generate ansible hosts and new_invoker.yml
            openwhisk_config_gen.generate_hosts_new_invokers(
                controller_vm_ips=controller_vm_ips, 
                invoker_vm_ips=exist_invoker_vm_ips, 
                new_invoker_vm_ips=new_invoker_vm_ips,
                host_ip=external_ips[host_node],
                config_dir=openwhisk_config_dir)
                    
            # the new_invoker_ids should be in the same order as 
            # the new_invokers in hosts file
            new_invoker_ids = [int(inv.replace('invoker', '')) for inv in sorted_new_invokers]
            openwhisk_config_gen.generate_new_invoker_yml(
                config_dir=openwhisk_config_dir, 
                new_invoker_ids=new_invoker_ids)
                    
            # scp hosts & yml to ansible directory on host node
            scp(source= openwhisk_config_dir / 'hosts.j2.ini', 
                target=username + '@' + external_ips[host_node] + ':' + azure_openwhisk_ansible_env_dir, 
                identity_file=str(rsa_private_key))
                
            scp(source= openwhisk_config_dir / 'new_invoker.yml', 
                target=username + '@' + external_ips[host_node] + ':' + azure_openwhisk_ansible_dir, 
                identity_file=str(rsa_private_key))
                
            # deploy new invokers
            azure_wsk_setup_cmd = 'cd ' + azure_openwhisk_ansible_dir + '; '
            azure_wsk_setup_cmd += './setup_add_invoker.sh'
            ssh(destination=username +'@' + external_ips[host_node],
                cmd=azure_wsk_setup_cmd,
                identity_file=rsa_private_key)
                
            azure_wsk_deploy_cmd = 'cd ' + azure_openwhisk_ansible_dir + '; '
            azure_wsk_deploy_cmd += './deploy_change_invoker.sh'
            ssh(destination=username +'@' + external_ips[host_node],
                cmd=azure_wsk_deploy_cmd,
                identity_file=rsa_private_key)
            
            wsk_deloy_end_time = time.time()
            logging.info('vm create time = %.2fs (%d vms), wsk deploy time = %.2fs' %(
                vm_create_end_time - vm_create_start_time, len(new_vms),
                wsk_deloy_end_time - vm_create_end_time))
            
            operation_log[op_time]['vm_creation_time'] = vm_create_end_time - vm_create_start_time
            operation_log[op_time]['wsk_deploy_time'] = wsk_deloy_end_time - vm_create_end_time
            operation_log[op_time]['new_vms'] = copy.copy(new_vms)
        
        elif update_config:
            # no new vm needs created, but some vms failed
            updated_invoker_roles = {}
            # include existing invokers
            for invoker in alive_invokers:
                updated_invoker_roles[invoker] = alive_invokers[invoker]
            deploy_config['nodes'] = nodes_config
            openwhisk_roles_config['invokers'] = updated_invoker_roles
            deploy_config['openwhisk_roles'] = openwhisk_roles_config
            with open(str(deploy_config_path), 'w+') as f:
                json.dump(deploy_config, f,  indent=4, sort_keys=True)
            #--- ips ---#
            with open(str(external_ip_path), "w+") as f:
                json.dump(external_ips, f, indent=4, sort_keys=True)
            with open(str(internal_ip_path), "w+") as f:
                json.dump(internal_ips, f, indent=4, sort_keys=True)
        
        if init_check or update_config:
            init_check = False
            # generate invoker_ips file & copy to host
            invoker_ips = {}
            for inv in openwhisk_roles_config['invokers']:
                vm = openwhisk_roles_config['invokers'][inv]
                invoker_ips[inv] = external_ips[vm]
            with open(str(openwhisk_config_dir / 'invoker_ips.json'), 'w+') as f:
                json.dump(invoker_ips, f, indent=4, sort_keys=True)
                
            scp(source= openwhisk_config_dir / 'invoker_ips.json', 
                target=username + '@' + external_ips[host_node] + ':~/', 
                identity_file=str(rsa_private_key))
            
            # # copy monitor to invokers
            # for inv in invoker_ips:
            #     scp(source= azure_scripts_dir / 'monitor_cpu.py', 
            #         target=username + '@' + invoker_ips[inv] + ':~/', 
            #         identity_file=str(rsa_private_key))

with open('./autoscale_op_log.json', 'w+') as f:
    json.dump(operation_log, f, indent=4, sort_keys=True)