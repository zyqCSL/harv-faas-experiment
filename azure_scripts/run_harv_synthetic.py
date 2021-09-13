import argparse
import sys
import os
import subprocess
import threading
import multiprocessing
import logging
from pathlib import Path
import time
import json
import shutil

logging.basicConfig(level=logging.INFO)

log_dir = Path.home() / 'synthetic_activation_log'
workloads_dir = Path.home() / 'openwhisk_workloads'
trace_replayer = workloads_dir / 'trace_replay' / 'replay_synthetic_trace.py'
openwhisk_archive = Path.home() / 'openwhisk_archive'
invoker_log_dir = Path.home() / 'invoker_logs'

os.makedirs(str(invoker_log_dir), exist_ok=True)
os.makedirs(str(log_dir), exist_ok=True)

invoker_ips = {}
invoker_vcpus = {}
invoker_cum_docker_cpu_time = {}
invoker_cpu_usage = {}
invoker_cpu_util = {}
invoker_prev_check_time = {}

def change_time(time_str):
    if 'h' in time_str:
        return int(time_str.replace('h', '')) * 60 * 60
    elif 'm' in time_str:
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

def run_workgen(workers, trace, exp_time):
    _stdout = sys.stdout
    _stderr = sys.stderr
    cmd = 'python3 ' + str(trace_replayer) + \
        ' --func-trace ' + str(trace) + \
        ' --workers ' + str(workers)
    if exp_time != '':
        cmd += ' --exp-time ' + exp_time
    p = subprocess.Popen(cmd, shell=True, stdout=_stdout, stderr=_stderr)
    return p

def read_db_data(dateback_sec, limit, output_dir):
    dateback_sec = int(dateback_sec)
    os.chdir(str(Path.home()))
    cmd = 'python3 azure_read_function_stats_resp.py' + \
        ' --dateback-sec ' + str(dateback_sec) + \
        ' --limit ' + str(limit) + \
        ' --output-dir ' + str(output_dir) + \
        ' --couchdb-config ' + str(db_config)
    subprocess.run(cmd, shell=True)

def get_invoker_vcpus(invoker_vcpus, invoker_name, invoker_ip, 
        username, start_time, quiet):
    cmd = 'cat /var/lib/hyperv/.kvp_pool_0'
    r = ssh_checkoutput(destination=username+'@'+invoker_ip, 
        cmd=cmd, quiet=quiet)
    if r != None:
        r = r.decode("utf-8")
        # print(r)
        r = [k for k in r.split("\u0000") if k != '']
        # invoker_vcpus[invoker_name] = {}
        # invoker_vcpus[invoker_name]['time'] = round(time.time() - start_time, 1)
        # invoker_vcpus[invoker_name]['val'] = float(r[-1])

        invoker_vcpus[invoker_name + '~time'] = round(time.time() - start_time, 1)
        invoker_vcpus[invoker_name + '~val'] = float(r[-1])

def get_invoker_docker_cpu_time(invoker_cpu_usage, invoker_name, invoker_ip, 
        username, start_time, quiet):
    # cmd = 'cat /sys/fs/cgroup/cpu/cgroup_harvest_vm/cpuacct.usage'
    cmd = 'cat /sys/fs/cgroup/cpu/cpuacct.usage'
    r = ssh_checkoutput(destination=username+'@'+invoker_ip, 
        cmd=cmd, quiet=quiet)
    if r != None:
        # print([invoker_name, r])
        r = float(r.decode("utf-8")) / (10**9)
        # print(r)
        # invoker_cpu_usage[invoker_name] = {}
        # invoker_cpu_usage[invoker_name]['val'] = r
        # invoker_cpu_usage[invoker_name]['time'] = round(time.time() - start_time, 1)

        # invoker_cpu_usage[invoker_name] = {}
        invoker_cpu_usage[invoker_name + '~val'] = r
        invoker_cpu_usage[invoker_name + '~time'] = round(time.time() - start_time, 1)

def monitor_invoker(invoker_ips, invoker_vcpus, 
        invoker_cum_docker_cpu_time, invoker_cpu_usage, invoker_cpu_util,
        invoker_prev_check_time, username, start_time):
    # get vcpus
    inv_vcpu_ret = {}
    threads = []
    manager = multiprocessing.Manager()
    raw_inv_vcpu_ret = manager.dict()
    for inv in invoker_ips:
        inv_ip = invoker_ips[inv]
        t = multiprocessing.Process(target=get_invoker_vcpus, kwargs={
                'invoker_vcpus': raw_inv_vcpu_ret,
                'invoker_name': inv,
                'invoker_ip': inv_ip,
                'username': username,
                'start_time': start_time,
                'quiet': True
            })
        t.start()
        threads.append(t)
    time.sleep(3.5)
    for t in threads:
        if t.is_alive():
            t.terminate()
        t.join()
    
    inv_cur_vcpus = {}
    # print(inv_vcpu_ret)
    inv_vcpu_ret = {}
    for inv_field in raw_inv_vcpu_ret:
        inv, field = inv_field.split('~')
        if inv not in inv_vcpu_ret:
            inv_vcpu_ret[inv] = {}
        inv_vcpu_ret[inv][field] = raw_inv_vcpu_ret[inv_field]
    
    for inv in inv_vcpu_ret:
        v = inv_vcpu_ret[inv]['val']
        t = inv_vcpu_ret[inv]['time']
        if inv not in invoker_vcpus:
            invoker_vcpus[inv] = {}
        invoker_vcpus[inv][t] = v
        inv_cur_vcpus[inv] = v

    # get cpu usage
    threads = []
    # inv_cpu_usage_ret = {}
    raw_inv_cpu_usage_ret = manager.dict()
    for inv in invoker_ips:
        inv_ip = invoker_ips[inv]
        t = multiprocessing.Process(target=get_invoker_docker_cpu_time, kwargs={
                'invoker_cpu_usage': raw_inv_cpu_usage_ret,
                'invoker_name': inv,
                'invoker_ip': inv_ip,
                'username': username,
                'start_time': start_time,
                'quiet': True
            })
        t.start()
        threads.append(t)

    time.sleep(3.5)
    for t in threads:
        if t.is_alive():
            t.terminate()
        t.join()
    
    inv_cpu_usage_ret = {}
    for inv_field in raw_inv_cpu_usage_ret:
        inv, field = inv_field.split('~')
        if inv not in inv_cpu_usage_ret:
            inv_cpu_usage_ret[inv] = {}
        inv_cpu_usage_ret[inv][field] = raw_inv_cpu_usage_ret[inv_field]
    
    for inv in inv_cpu_usage_ret:
        v = inv_cpu_usage_ret[inv]['val']
        t = inv_cpu_usage_ret[inv]['time']
        if inv in invoker_cum_docker_cpu_time:
            cpu_time = v - invoker_cum_docker_cpu_time[inv]
            # print('%s cpu time = %.4f' %(inv, cpu_time))
            if inv in invoker_prev_check_time and inv in inv_cur_vcpus:
                cpu_usage = cpu_time / (t - invoker_prev_check_time[inv])
                cpu_util = cpu_usage / inv_cur_vcpus[inv]
                if inv not in invoker_cpu_usage:
                    invoker_cpu_usage[inv] = {}
                if inv not in invoker_cpu_util:
                    invoker_cpu_util[inv] = {}
                invoker_cpu_usage[inv][t] = cpu_usage
                invoker_cpu_util[inv][t] = cpu_util
        invoker_cum_docker_cpu_time[inv] = v
        invoker_prev_check_time[inv] = t

# -----------------------------------------------------------------------
# parser args definition
# -----------------------------------------------------------------------
parser = argparse.ArgumentParser()
# parser.add_argument('--users', dest='users', type=int, required=True)
parser.add_argument('--username', dest='username', type=str, default='yanqi')
parser.add_argument('--exp-time', dest='exp_time', type=str, default='')
parser.add_argument('--interval', dest='interval', type=str, default='10s')
parser.add_argument('--invoker-ips', dest='invoker_ips', type=str, required=True)
parser.add_argument('--func-trace', dest='function_trace', type=str, required=True)
parser.add_argument('--workers', dest='workers', type=int, default=30)
parser.add_argument('--openwhisk-version', dest='openwhisk_version',
                    type=str, default='openwhisk-harv-vm-cgroup-azure-distributed')

# -----------------------------------------------------------------------
# parse args
# -----------------------------------------------------------------------
args = parser.parse_args()
openwhisk_dir = openwhisk_archive / args.openwhisk_version
ansible_dir = openwhisk_dir / 'ansible'
db_config = ansible_dir / 'db_local.ini'
# users = args.users
exp_time = args.exp_time
if exp_time != '':
    exp_time_sec = change_time(exp_time)
else:
    exp_time_sec = -1
interval = change_time(args.interval)
invoker_ip_file = args.invoker_ips
with open(args.invoker_ips, 'r') as f:
    invoker_ips = json.load(f)
username = args.username
workers = args.workers
function_trace = args.function_trace
trace_time = 0
trace_inv_num = 0
with open(function_trace, 'r') as f:
    d = json.load(f)
    trace_inv_num = len(d)
    trace_time = d[-1]['start_time'] - d[0]['start_time']
    print('trace_time = %ds' %trace_time)
    assert trace_time > 0
    if exp_time_sec <= 0:
        exp_time_sec = trace_time
# -----------------------------------------------------------------------
# actual experiment
# -----------------------------------------------------------------------

# warm up cgroup
os.makedirs(str(invoker_log_dir), exist_ok=True)

# start work gen
p = run_workgen(workers=workers, trace=function_trace, exp_time=exp_time)
main_loop_time = min(exp_time_sec, trace_time)

start_time = time.time()
prev_period = 0
while True:
    cur_time = time.time() - start_time
    if cur_time >= main_loop_time:
        break
    if cur_time - prev_period < interval:
        time.sleep(interval - (cur_time - prev_period))
    prev_period = cur_time
    with open(args.invoker_ips, 'r') as f:
        invoker_ips = json.load(f)
    monitor_invoker(invoker_ips=invoker_ips, 
        invoker_vcpus=invoker_vcpus, 
        invoker_cum_docker_cpu_time=invoker_cum_docker_cpu_time, 
        invoker_cpu_usage=invoker_cpu_usage, 
        invoker_cpu_util=invoker_cpu_util,
        invoker_prev_check_time=invoker_prev_check_time, 
        username=username, 
        start_time=start_time)
    print('At time %.1f' %(time.time() - start_time))
    # print('invoker_vcpus')
    # print(invoker_vcpus)
    print('invoker_cpu_usage')
    for inv in invoker_cpu_usage:
        lt = max(list(invoker_cpu_usage[inv].keys()))
        print('%s cpu_usage = %.4f' %(inv, invoker_cpu_usage[inv][lt]))
    # print('invoker_cpu_util')
    # print(invoker_cpu_util)

p.wait()
dateback_sec = int(time.time() - start_time) + 10
read_db_data(dateback_sec=dateback_sec,
    limit=trace_inv_num,
    output_dir=log_dir)

with open(str(invoker_log_dir / 'vcpus.json'), 'w+') as f:
    json.dump(invoker_vcpus, f, indent=4, sort_keys=True)

with open(str(invoker_log_dir / 'cpu_usage.json'), 'w+') as f:
    json.dump(invoker_cpu_usage, f, indent=4, sort_keys=True)

with open(str(invoker_log_dir / 'cpu_util.json'), 'w+') as f:
    json.dump(invoker_cpu_util, f, indent=4, sort_keys=True)