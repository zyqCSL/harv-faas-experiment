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
openwhisk_dir = Path.home() / 'openwhisk_archive' / 'openwhisk-harv-vm-cgroup-azure-distributed'
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

def ssh_checkoutput(destination, cmd, quiet=False):
    _stderr = sys.stderr
    if quiet:
        _stderr = subprocess.DEVNULL
    cmd = 'ssh -q -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' + \
        str(destination) + ' \"' + cmd + '\"'
    if not quiet:
        print("ssh cmd = " + cmd)
    try: 
        r = subprocess.check_output(cmd, shell=True, stderr=_stderr, timeout=3)
        return r
    except Exception as e:
        logging.error(e)
        return None

def run_locust(exp_time, users):
    os.chdir(str(locust_dir))
    workers = max(1, users // 10)
    cmd = 'USERS=%d EXP_TIME=%ds docker-compose -f docker-compose-serverless-mix.yml up --scale worker=%d' %(
        users, exp_time, workers)
    subprocess.run(cmd, shell=True)
    time.sleep(5)

def read_db_data(dateback_sec, limit, output_dir):
    dateback_sec = int(dateback_sec)
    os.chdir(str(Path.home()))
    cmd = 'python3 azure_read_function_stats_resp.py' + \
        ' --dateback-sec ' + str(dateback_sec) + \
        ' --limit ' + str(limit) + \
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

# -----------------------------------------------------------------------
# parse args
# -----------------------------------------------------------------------
args = parser.parse_args()
# users = args.users
exp_time = change_time(args.exp_time)
interval = args.interval
# -----------------------------------------------------------------------
# actual experiment
# -----------------------------------------------------------------------
for users in [10, 25, 50, 100, 150, 200, 225, 250, 275, 300]:
    os.makedirs(str(invoker_log_dir), exist_ok=True)
    # start work gen
    run_locust(exp_time, users)
    total_req = int(users * exp_time / 10)
    read_db_data(dateback_sec=exp_time, limit=total_req, output_dir=log_dir)
    copy_locust_logs(users)

    logging.info('Start cooling down...')
    time.sleep(605)     # 600s is the default container kill time of openwhisk
    logging.info('Cool down completes')