import argparse
import sys
import os
import subprocess
import threading
import logging
from pathlib import Path
import time
import json
import shutil

logging.basicConfig(level=logging.INFO)

log_dir = Path.home() / 'openwhisk_locust_log'
workloads_dir = Path.home() / 'openwhisk_workloads'
locust_dir = workloads_dir / 'openwhisk_locust'
openwhisk_dir = Path.home() / 'openwhisk_archive' / 'openwhisk-mem-compare'
ansible_dir = openwhisk_dir / 'ansible'
db_config = ansible_dir / 'db_local.ini'
monitor_path = Path.home() / 'monitor_cpu.py'
invoker_log_dir = Path.home() / 'invoker_logs'

os.makedirs(str(invoker_log_dir), exist_ok=True)

def change_time(time_str):
	if 'm' in time_str:
		return int(time_str.replace('m', '')) * 60
	elif 's' in time_str:
		return int(time_str.replace('s', ''))
	else:
		return int(time_str)

def scp(source, target, quiet=False):
    _stdout = sys.stdout
    _stderr = sys.stderr
    if quiet:
        _stdout = subprocess.DEVNULL
        _stderr = subprocess.DEVNULL
    cmd = 'scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ' + \
        str(source) + ' ' + str(target)
    subprocess.run(cmd, shell=True, stdout=_stdout, stderr=_stderr)

def ssh(destination, cmd, quiet=False):
    _stdout = sys.stdout
    _stderr = sys.stderr
    if quiet:
        _stdout = subprocess.DEVNULL
        _stderr = subprocess.DEVNULL
    cmd = 'ssh -q -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' + \
        str(destination) + ' \"' + cmd + '\"'
    if not quiet:
        print("ssh cmd = " + cmd)
    subprocess.run(cmd, shell=True, stdout=_stdout, stderr=_stderr)

def clear_openwhisk():
    os.chdir(str(ansible_dir))
    cmd = './clear_deployment.sh'
    subprocess.run(cmd, shell=True)
    time.sleep(5)

def copy_wsk():
    cmd = 'cp ' + str(Path.home() / 'openwhisk_archive' / 'wsk') + ' ' + str(openwhisk_dir / 'bin')
    subprocess.run(cmd, shell=True)
    time.sleep(5)

# todo: actually redeploy, split to deploy & redeploy later
def deploy_openwhisk():
    os.chdir(str(ansible_dir))
    cmd = './deploy_couchdb.sh'
    subprocess.run(cmd, shell=True)
    time.sleep(5)

def register_actions():
    os.chdir(str(workloads_dir))
    cmd = 'python3 register_copy_actions.py'
    subprocess.run(cmd, shell=True)
    time.sleep(5)

def run_locust(exp_time, users):
    os.chdir(str(locust_dir))
    workers = max(1, users // 10)
    cmd = 'USERS=%d EXP_TIME=%ds docker-compose -f docker-compose-serverless-mix.yml up --scale worker=%d' %(
        users, exp_time, workers)
    subprocess.run(cmd, shell=True)
    time.sleep(5)

def read_db_data(dateback_s, output_dir):
    os.chdir(str(Path.home()))
    cmd = 'python3 azure_read_function_stats.py' + \
        ' --dateback-s ' + str(dateback_s) + \
        ' --output-dir ' + str(output_dir) + \
        ' --couchdb-config ' + str(db_config)
    subprocess.run(cmd, shell=True)

def copy_locust_logs(users):
    if os.path.isdir(str(log_dir) + '_users_' + str(users)):
        shutil.rmtree(str(log_dir) + '_users_' + str(users))
    cmd = 'cp -r ' + str(log_dir) + ' ' + str(log_dir) + '_users_' + str(users)
    subprocess.run(cmd, shell=True)

def monitor_invoker(invoker, invoker_ip, exp_time, interval, trace, use_server_cgroup):
    invoker_log = invoker + '_log.json'
    cmd = 'python3 monitor_cpu.py --log ' + invoker_log + \
        ' --exp-time ' + str(exp_time) + \
        ' --interval ' + str(interval)
    if trace != '':
        cmd += ' --trace ' + trace
    if use_server_cgroup:
        cmd += ' --use-server-cgroup'
    ssh(destination = invoker_ip, cmd = cmd)
    scp(source = invoker_ip+':~/'+invoker_log, target = str(invoker_log_dir)+'/')

def emulate_harvest_vm(invoker_ip, exp_time, trace, physical_core=True):
    cmd = 'sudo python3 harvest_vm_emulator_mem_compare.py --trace ' + trace + \
        ' --exp-time ' + str(exp_time)
    if physical_core:
        cmd += ' --physical-core'
    ssh(destination=invoker_ip, cmd=cmd)

def rename_invoker_logs(users):
    if os.path.isdir(str(invoker_log_dir) + '_users_' + str(users)):
        shutil.rmtree(str(invoker_log_dir) + '_users_' + str(users))
    cmd = 'mv ' + str(invoker_log_dir) + ' ' + str(invoker_log_dir) + '_users_' + str(users)
    subprocess.run(cmd, shell=True)

# -----------------------------------------------------------------------
# parser args definition
# -----------------------------------------------------------------------
parser = argparse.ArgumentParser()
# parser.add_argument('--users', dest='users', type=int, required=True)
parser.add_argument('--exp-time', dest='exp_time', type=str, required=True)
parser.add_argument('--interval', dest='interval', type=int, default=1)
parser.add_argument('--invoker-ips', dest='invoker_ips', type=str, required=True)
parser.add_argument('--deploy', dest='deploy', action='store_true')
parser.add_argument('--emul-harv-vm', dest='emul_harv_vm', action='store_true')
parser.add_argument('--trace-physical-core', dest='trace_physical_core', action='store_true')
parser.add_argument('--use-server-cgroup', dest='use_server_cgroup', action='store_true')

# -----------------------------------------------------------------------
# parse args
# -----------------------------------------------------------------------
args = parser.parse_args()
# users = args.users
exp_time = change_time(args.exp_time)
interval = args.interval
deploy = args.deploy
emul_harv_vm = args.emul_harv_vm
trace_physical_core = args.trace_physical_core
with open(args.invoker_ips, 'r') as f:
    invoker_ips = json.load(f)
use_server_cgroup = args.use_server_cgroup
# -----------------------------------------------------------------------
# actual experiment
# -----------------------------------------------------------------------

# warm up cgroup
if emul_harv_vm:
    emul_warmup = {}
    for invoker in invoker_ips:
        t = threading.Thread(target=emulate_harvest_vm, kwargs={
            'invoker_ip': invoker_ips[invoker],
            'exp_time': 100,
            'trace': invoker + '.txt',
            'physical_core': trace_physical_core
        })
        emul_warmup[invoker] = t
        t.start()
    for t in emul_warmup:
        emul_warmup[t].join()


for users in [10, 25, 50, 100, 150, 200, 225, 250, 275, 300]:
    os.makedirs(str(invoker_log_dir), exist_ok=True)
    if deploy:
        clear_openwhisk()     # clear deployment also clears function stats
        copy_wsk()
        deploy_openwhisk()
        register_actions()

    # start monitor threads
    monitor_threads = {}
    for invoker in invoker_ips:  
        inv_trace = ''
        if emul_harv_vm:
            inv_trace = invoker + '.txt'    
        t = threading.Thread(target=monitor_invoker, kwargs={
            'invoker': invoker,
            'invoker_ip': invoker_ips[invoker],
            'exp_time': exp_time,
            'interval': interval,
            'trace' : inv_trace,
            'use_server_cgroup': use_server_cgroup
        })
        monitor_threads[invoker] = t
        t.start()

    # start harvest vm emulators
    harv_vm_emulators = {}
    if emul_harv_vm:
        for invoker in invoker_ips:
            t = threading.Thread(target=emulate_harvest_vm, kwargs={
                'invoker_ip': invoker_ips[invoker],
                'exp_time': exp_time,
                'trace': invoker + '.txt',
                'physical_core': trace_physical_core
            })
            harv_vm_emulators[invoker] = t
            t.start()

    # start work gen
    run_locust(exp_time, users)

    # wait for emulators to stop
    for inv in harv_vm_emulators:
        harv_vm_emulators[inv].join()

    # collect data
    rename_invoker_logs(users)
    for inv in monitor_threads:
        monitor_threads[inv].join()

    read_db_data(dateback_s=exp_time, output_dir=log_dir)
    copy_locust_logs(users)

    logging.info('Start cooling down...')
    if not deploy:
        time.sleep(605)     # 600s is the default container kill time of openwhisk
    else:
        time.sleep(10)
    logging.info('Cool down completes')