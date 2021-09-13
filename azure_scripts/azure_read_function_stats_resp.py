# test
# python3 ./profile_function.py --min-users 1 --max-users 2 --user-step 1 --exp-time 60s --profile-users 1 --profile-time 60s --warmup-time 30s --function mobilenet 
# python3 ./profile_function.py --min-users 5 --max-users 30 --user-step 5 --profile-users 10 --function mobilenet

# Check https://github.com/apache/openwhisk/blob/master/docs/annotations.md
# for couchdb record annotations
# the unit of time metric should be milliseconds

# assume docker version >= 1.13
import os
import time
import numpy as np
import argparse
import logging
import subprocess
import csv
import base64
import json

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from pathlib import Path

parser = argparse.ArgumentParser()
# parser.add_argument('--cpus', dest='cpus', type=int, required=True)
# parser.add_argument('--stack-name', dest='stack_name', type=str, required=True)
parser.add_argument('--dateback-sec', dest='dateback_sec', type=int, required=True)
parser.add_argument('--limit', dest='limit', type=int, default=50000)
parser.add_argument('--output-dir', dest='output_dir', type=str, required=True)
parser.add_argument('--couchdb-config', dest='couchdb_config', type=str, required=True)
parser.add_argument('--detail-lat', dest='detail_lat', action='store_true')

def change_time(time_str):
    if 'h' in time_str:
        return int(time_str.replace('h', '')) * 60 * 60
    elif 'm' in time_str:
        return int(time_str.replace('m', '')) * 60
    elif 's' in time_str:
        return int(time_str.replace('s', ''))
    else:
        return int(time_str)

args = parser.parse_args()
dateback_sec = args.dateback_sec
limit = args.limit
output_dir = Path(args.output_dir)

percentiles = [25, 50, 75, 90, 95, 99]
if args.detail_lat:
    percentiles = list(range(0, 101, 1))

# CrouchDB (from #OPENWHISK_DIR/ansible/db_local.ini)
'''
[db_creds]
db_provider=CouchDB
db_username=yz2297
db_password=openwhisk_couch
db_protocol=http
db_host=128.253.128.68
db_port=5984

[controller]
db_username=whisk_local_controller0
db_password=some_controller_passw0rd

[invoker]
db_username=whisk_local_invoker0
db_password=some_invoker_passw0r
'''
DB_PROVIDER = ''
DB_USERNAME = ''
DB_PASSWORD = ''
DB_PROTOCOL = ''
DB_HOST = ''
DB_PORT = ''
with open(args.couchdb_config, 'r') as f:
    lines = f.readlines()[0:7]
    for line in lines:
        if '=' not in line:
            continue
        field, val = line.strip().split('=')
        if field == 'db_provider':
            DB_PROVIDER = val
        elif field == 'db_username':
            DB_USERNAME = val
        elif field == 'db_password':
            DB_PASSWORD = val
        elif field == 'db_protocol':
            DB_PROTOCOL = val
        elif field == 'db_host':
            DB_HOST = val
        elif field == 'db_port':
            DB_PORT = val

assert DB_PROVIDER != ''
assert DB_USERNAME != ''
assert DB_PASSWORD != ''
assert DB_PROTOCOL != ''
assert DB_HOST != ''
assert DB_PORT != ''

# -----------------------------------------------------------------------
# miscs
# -----------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)

# -----------------------------------------------------------------------
# couch db utilities
# -----------------------------------------------------------------------

def get_activation_since(since, limit=50000):
    """
    Returns the activation IDs (including the namespace)
    """
    res = requests.post(url=DB_PROTOCOL + '://' + DB_HOST + ':' + DB_PORT + '/' + 'whisk_local_activations/_find',
                        json={
                            "selector": {
                                "start": {
                                    "$gte": since
                                }
                            },
                            "fields": ['activationId', 'annotations', 'duration', 'end', 'name', 'namespace', 'start', 'response'],
                            "limit": limit
                        },
                        auth=(DB_USERNAME, DB_PASSWORD))
    doc = json.loads(res.text)['docs']
    return doc


# read activation data from db
activations = get_activation_since(since=int(time.time()*1000) - dateback_sec*1000, 
	limit=limit)
action_records = {}    # per action
merged_action_records = {}    # per action type
all_action_records = {}
all_action_records['num_total'] = 0
all_action_records['num_cold'] = 0
all_action_records['wait'] = []
all_action_records['init'] = []
all_action_records['duration'] = []
all_action_records['total'] = []
# activation status 
all_action_records['success'] = 0
all_action_records['application_error'] = 0
all_action_records['action_dev_error'] = 0
all_action_records['wsk_internal_error'] = 0

class ActivationRecord:
    def __init__(self, start_time, duration):
        self.start_time = start_time
        self.duration = duration
# all_activation_records = []

for record in activations:
    duration = record['duration']
    # all_activation_records.append(ActivationRecord(start_time=record['start'], 
    #     duration=record['duration']))
    wait = 0
    init = 0
    for d in record['annotations']:
        if d['key'] == 'waitTime':
            wait = d['value']
        if d['key'] == 'initTime':
            init = d['value']
    status_code = record['response']['statusCode']
    action = record['name']
    merged_action = action.split('-')[0]
    # print('%s d=%d w=%d' %(action, duration, wait))
    if action not in action_records:
        action_records[action] = {}
        action_records[action]['wait'] = []
        action_records[action]['init'] = []
        action_records[action]['duration'] = []
        action_records[action]['total'] = []
        action_records[action]['num_total'] = 0
        action_records[action]['num_cold'] = 0
        # status
        action_records[action]['success'] = 0
        action_records[action]['application_error'] = 0
        action_records[action]['action_dev_error'] = 0
        action_records[action]['wsk_internal_error'] = 0

    if merged_action not in merged_action_records:
        merged_action_records[merged_action] = {}
        merged_action_records[merged_action]['wait'] = []
        merged_action_records[merged_action]['init'] = []
        merged_action_records[merged_action]['duration'] = []
        merged_action_records[merged_action]['total'] = []
        merged_action_records[merged_action]['num_total'] = 0
        merged_action_records[merged_action]['num_cold'] = 0
        # status
        merged_action_records[merged_action]['success'] = 0
        merged_action_records[merged_action]['application_error'] = 0
        merged_action_records[merged_action]['action_dev_error'] = 0
        merged_action_records[merged_action]['wsk_internal_error'] = 0
    
    if status_code == 0:    # success
        all_action_records['success'] += 1
        action_records[action]['success'] += 1
        merged_action_records[merged_action]['success'] += 1
    elif status_code == 1:    # application error
        all_action_records['application_error'] += 1
        action_records[action]['application_error'] += 1
        merged_action_records[merged_action]['application_error'] += 1
    elif status_code == 2:    # action developer error
        all_action_records['action_dev_error'] += 1
        action_records[action]['action_dev_error'] += 1
        merged_action_records[merged_action]['action_dev_error'] += 1
    elif status_code == 3:    # whisk internal error
        all_action_records['wsk_internal_error'] += 1
        action_records[action]['wsk_internal_error'] += 1
        merged_action_records[merged_action]['wsk_internal_error'] += 1

    action_records[action]['init'].append(init)
    action_records[action]['wait'].append(wait)
    action_records[action]['duration'].append(duration)
    action_records[action]['total'].append(duration+wait+init)
    action_records[action]['num_total'] += 1
    if init > 0:
        action_records[action]['num_cold'] += 1

    merged_action_records[merged_action]['init'].append(init)
    merged_action_records[merged_action]['wait'].append(wait)
    merged_action_records[merged_action]['duration'].append(duration)
    merged_action_records[merged_action]['total'].append(duration+wait+init)
    merged_action_records[merged_action]['num_total'] += 1
    if init > 0:
        merged_action_records[merged_action]['num_cold'] += 1

    if 'synthetic' in action:
        all_action_records['init'].append(init)
        all_action_records['wait'].append(wait)
        all_action_records['duration'].append(duration)
        all_action_records['total'].append(duration+wait+init)
        all_action_records['num_total'] += 1
    if init > 0:
        all_action_records['num_cold'] += 1
            
for action in action_records:
    action_records[action]['init'] = np.array(action_records[action]['init'])
    action_records[action]['wait'] = np.array(action_records[action]['wait'])
    action_records[action]['duration'] = np.array(action_records[action]['duration'])
    action_records[action]['total'] = np.array(action_records[action]['total'])

for action in merged_action_records:
    merged_action_records[action]['init'] = np.array(merged_action_records[action]['init'])
    merged_action_records[action]['wait'] = np.array(merged_action_records[action]['wait'])
    merged_action_records[action]['duration'] = np.array(merged_action_records[action]['duration'])
    merged_action_records[action]['total'] = np.array(merged_action_records[action]['total'])

with open(str(output_dir / ('latency_duration_raw.json')), 'w+') as f:
    json.dump(all_action_records['total'], f, indent=4)

all_action_records['init'] = np.array(all_action_records['init'])
all_action_records['wait'] = np.array(all_action_records['wait'])
all_action_records['duration'] = np.array(all_action_records['duration'])
all_action_records['total'] = np.array(all_action_records['total'])
all_action_records['init'] = np.array(all_action_records['init'])

action_names = sorted(list(action_records.keys()))
merged_action_names = sorted(list(merged_action_records.keys()))

for field in ['init', 'wait', 'duration', 'total']:
    with open(str(output_dir / ('latency_' + field + '.csv')), 'w+') as f:
        lat_writer = csv.writer(f, delimiter=',')
        first_row = ['name'] + [str(k) for k in percentiles]
        lat_writer.writerow(first_row)
        for action in action_names:
            row = [action]
            for p in percentiles:
                l = np.percentile(action_records[action][field], p, interpolation='nearest')
                row.append(l)
            lat_writer.writerow(row)

        for action in merged_action_names:
            row = [action]
            for p in percentiles:
                l = np.percentile(merged_action_records[action][field], p, interpolation='nearest')
                row.append(l)
            lat_writer.writerow(row)
        
        row = ['all']
        for p in percentiles:
            l = np.percentile(all_action_records[field], p, interpolation='nearest')
            row.append(l)
        lat_writer.writerow(row)
    
with open(str(output_dir / ('cold_start_rate.csv')), 'w+') as f:
    rate_writer = csv.writer(f, delimiter=',')
    rate_writer.writerow(['name', 'cold_start_rate(%)'])
    for action in action_names:
        row = [action]
        row.append(round(action_records[action]['num_cold']/action_records[action]['num_total']*100, 2))
        rate_writer.writerow(row)
        
    for action in merged_action_names:
        row = [action]
        row.append(round(merged_action_records[action]['num_cold']/merged_action_records[action]['num_total']*100, 2))
        rate_writer.writerow(row)
        
    row = ['all']
    row.append(round(all_action_records['num_cold']/all_action_records['num_total']*100, 2))
    rate_writer.writerow(row)

with open(str(output_dir / ('activation_status.csv')), 'w+') as f:
    status_writer = csv.writer(f, delimiter=',')
    status_writer.writerow(['name', 'success', 'application_error', 'action_dev_error', 'wsk_internal_error'])
    for action in action_names:
        row = [action, 
            action_records[action]['success'],
            action_records[action]['application_error'],
            action_records[action]['action_dev_error'],
            action_records[action]['wsk_internal_error']
        ]
        status_writer.writerow(row)
        
    for action in merged_action_names:
        row = [action, 
            merged_action_records[action]['success'],
            merged_action_records[action]['application_error'],
            merged_action_records[action]['action_dev_error'],
            merged_action_records[action]['wsk_internal_error']
        ]
        status_writer.writerow(row)
        
    row = ['all', 
            all_action_records['success'],
            all_action_records['application_error'],
            all_action_records['action_dev_error'],
            all_action_records['wsk_internal_error']
        ]
    status_writer.writerow(row)

