import os
import sys
import time
import argparse
import subprocess
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)

hyperv_kvp = Path('/var/lib/hyperv/')
core_hyperv_kvp = hyperv_kvp / '.kvp_pool_0'
mem_hyperv_kvp  = hyperv_kvp / '.kvp_pool_2'
cgroup = Path('/sys/fs/cgroup')
harv_vm_cpu_cgroup = cgroup / 'cpu' / 'cgroup_harvest_vm'
harv_vm_mem_cgroup = cgroup / 'memory' / 'cgroup_harvest_vm'

# -----------------------------------------------------------------------
# parser args definition
# -----------------------------------------------------------------------
parser = argparse.ArgumentParser()
# parser.add_argument('--cpus', dest='cpus', type=int, required=True)
# parser.add_argument('--stack-name', dest='stack_name', type=str, required=True)
parser.add_argument('--trace', dest='trace', type=str, required=True)
parser.add_argument('--exp-time', dest='exp_time', type=int, required=True) # in seconds
parser.add_argument('--physical-core', dest='physical_core', action='store_true')

# -----------------------------------------------------------------------
# parse args
# -----------------------------------------------------------------------
args = parser.parse_args()
trace = args.trace
exp_time = args.exp_time            # experiment time in seconds
physical_core = args.physical_core  # set to true if trace shows physical core number

# check cfs sched period
cfs_period = 100000
with open(str(harv_vm_cpu_cgroup / "cpu.cfs_period_us"), 'r') as f:
    lines = f.readlines()
    assert len(lines) == 1
    cfs_period = int(lines[0].replace("\n", ""))
    logging.info("cpu.cfs_period_us = %d" %cfs_period)

# parse core number trace
event_time = []
event_core = []
with open(trace, 'r') as f:
    lines = f.readlines()
    for line in lines:
        if line == "\n" or line == "":
            continue
        data = [float(k) for k in line.split(' ') if (k != '' and k != '\n')]
        # print items
        assert len(data) == 2
        t = data[0]
        c = data[1]
        if len(event_time) > 0:
            assert event_time[-1] < t
        # logging.info("%d    %d" %(t, c))
        event_time.append(t)
        if physical_core:
            event_core.append(c * 2)
        else:
            event_core.append(c)

# event loop to emulate cpu changes
cur_trace_time = 0
start_time = time.time()
event_pointer  = 0

while event_pointer < len(event_time):
    cur_time = time.time()
    if cur_time - start_time >= event_time[event_pointer]:
        # loggin.info("event_pointer: %d" %event_pointer)
        # loggin.info("elapsed time: %.2f" %(cur_time - start_time))
        # loggin.info("event_time: %d" %event_time[event_pointer])

        #----------- currently only set cpu limit of cgroup ------------#
        # change hyperv kvp files
        virtual_core_num = event_core[event_pointer]
        with open(str(core_hyperv_kvp), "w") as f:
            line = 'CurrentCoreCount\0\0\0\0\0\0%.1f\0\0\0\0\0\0' %virtual_core_num
            f.write(line)
        # change cgroup cpu limit
        with open(str(harv_vm_cpu_cgroup / "cpu.cfs_quota_us"), "w") as f:
            f.write(str(int(cfs_period * virtual_core_num)) + "\n")
        event_pointer += 1
    elif event_time[event_pointer] >= exp_time:
        # check if time exceeds running time
        break
    else:
        wait_time = event_time[event_pointer] - (cur_time - start_time)
        time.sleep(wait_time)