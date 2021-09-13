import argparse
import sys
import os
import subprocess
from pathlib import Path
import time
import json

hyperv_file = Path('/var/lib/hyperv/.kvp_pool_0')
harvest_cgroup_cpu = Path('/sys/fs/cgroup/cpu/cgroup_harvest_vm/') / 'cpuacct.usage'
harvest_cgroup_mem = Path('/sys/fs/cgroup/memory/cgroup_harvest_vm/') / 'memory.stat'

def change_time(time_str):
	if 'm' in time_str:
		return int(time_str.replace('m', '')) * 60
	elif 's' in time_str:
		return int(time_str.replace('s', ''))
	else:
		return int(time_str)

def read_cpu_time():
    with open(str(harvest_cgroup_cpu), 'r') as f:
        lines = f.readlines()
        cpu_time_us = int(lines[0])
        return cpu_time_us

# -----------------------------------------------------------------------
# parser args definition
# -----------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument('--log', dest='log', type=str, required=True)
parser.add_argument('--exp-time', dest='exp_time', type=str, required=True)
parser.add_argument('--interval', dest='interval', type=int, required=True)
parser.add_argument('--trace', dest='trace', type=str, default='')
parser.add_argument('--use-server-cgroup', dest='use_server_cgroup', action='store_true')

# -----------------------------------------------------------------------
# parse args
# -----------------------------------------------------------------------
args = parser.parse_args()
log_path = Path.home() / args.log
exp_time = change_time(args.exp_time)
interval = args.interval
trace = args.trace
if args.use_server_cgroup:
    harvest_cgroup_cpu = Path('/sys/fs/cgroup/cpu') / 'docker' / 'cpuacct.usage'
    harvest_cgroup_mem = Path('/sys/fs/cgroup/memory') / 'docker' / 'memory.stat'

init_cpu_time = read_cpu_time()
prev_cpu_time = init_cpu_time
cpu_usage_log = []

init_time = time.time()
cur_time = init_time
prev_time = cur_time

while time.time() - init_time <= exp_time:
    cur_time = time.time()
    if cur_time - prev_time < interval:
        time.sleep(interval - (cur_time - prev_time))
    else:
        elapsed_time = cur_time - prev_time
        prev_time = cur_time
        cur_cpu_time = read_cpu_time()    # nanoseconds
        interval_cpu_time = cur_cpu_time - prev_cpu_time
        prev_cpu_time = cur_cpu_time
        cpu_usage = round(interval_cpu_time / (10**9) / (elapsed_time), 2)
        cpu_usage_log.append(cpu_usage)

total_time = time.time() - init_time
mean_cpu_usage = (prev_cpu_time - init_cpu_time) / (10**9) / total_time

log_data = {}
log_data['cpu_usage_history'] = cpu_usage_log
log_data['mean_cpu_usage'] = round(mean_cpu_usage, 2)

if trace == '':
    # not emulating for harvest vms, read aggregate cpu from kvp
    core_num = 0
    with open('/var/lib/hyperv/.kvp_pool_0', 'r') as f:
        data = [k for k in f.readlines()[0].split('\0') if (k != '' and k != '\n')]
        for i, d in enumerate(data):
            if d == 'CurrentCoreCount':
                core_num = float(data[i + 1])
    assert core_num != 0
    mean_cpu_util = mean_cpu_usage / core_num
    log_data['mean_cpu_util'] = round(mean_cpu_util, 2)
else:
    # emulating harvest vm, read aggregate cpu from trace
    total_cpu_time = 0
    prev_t = -1
    prev_c = -1
    with open(trace, 'r') as f:
        lines = f.readlines()
        for line in lines:
            if line == '\n' or line == '':
                continue
            data = [float(k) for k in line.split(' ') if (k != '' and k != '\n')]
            assert len(data) == 2
            t = data[0]
            c = data[1]
            if prev_t < 0:
                assert t == 0
            if prev_t >= 0:
                assert exp_time > prev_t
                total_cpu_time += (min(t, exp_time) - prev_t) * prev_c
            prev_t = t
            prev_c = c
            if t >= exp_time:
                break
    if prev_t < exp_time:
        total_cpu_time += (exp_time - prev_t) * prev_c
    total_cpu_time = total_cpu_time * 2 # assume trace shows physical cores
    mean_cpu_util = (prev_cpu_time - init_cpu_time) / (10**9) / total_cpu_time
    log_data['mean_cpu_util'] = round(mean_cpu_util, 3)

with open(str(log_path), 'w+') as f:
    json.dump(log_data, f, indent=4, sort_keys=True)