# test
# python3 ./profile_function.py --min-users 1 --max-users 2 --user-step 1 --exp-time 60s --profile-users 1 --profile-time 60s --warmup-time 30s --function mobilenet 
# python3 ./profile_function.py --min-users 5 --max-users 30 --user-step 5 --profile-users 10 --function mobilenet

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
parser.add_argument('--locust-log', dest='locust_log', type=str, required=True)
parser.add_argument('--output-dir', dest='output_dir', type=str, required=True)
parser.add_argument('--couchdb-config', dest='couchdb_config', type=str, required=True)

args = parser.parse_args()
locust_log = args.locust_log
output_dir = Path(args.output_dir)

percentiles = [25, 50, 75, 90, 95, 99]

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

def get_activation_ids_since(since, limit=100):
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
							"limit": limit
						},
						auth=(DB_USERNAME, DB_PASSWORD))
	doc = json.loads(res.text)
	for y in doc["docs"]:
		print(y.keys())
		print(y['annotations'])
	IDs = [x['_id'] for x in doc["docs"]]

	return IDs

def get_activations():
	headers = {
		 'Content-Type': 'application/json',
	 }

	res = requests.get(url=DB_PROTOCOL + '://' + DB_HOST + ':' + DB_PORT + '/' + 'whisk_local_activations/_all_docs',
						auth=(DB_USERNAME, DB_PASSWORD), 
						headers=headers)
	activations = json.loads(res.text)
	for item in activations:
		print(item)
		# print(activations[item])
		# print(item.keys())
		# print(json.loads(item['value']))
	for item in activations['rows']:
		print(item)
	return activations

# activations = get_activations()
ids = get_activation_ids_since(0)
print(ids)
# print(activations)

def get_activation_by_id(activation_id, namespace='guest'):
	 url = DB_PROTOCOL + '://' + DB_HOST + ':' + DB_PORT + '/' + 'whisk_local_activations/' + \
		 namespace + '%2F' + activation_id

	 headers = {
		 'Content-Type': 'application/json',
	 }

	 res = requests.get(url=url,
						 headers=headers,
						 auth=(DB_USERNAME, DB_PASSWORD))

	 activation = json.loads(res.text)
	 if 'duration' not in activation or 'annotations' not in activation:
		 print("Incomplete activation")
		 print(activation)
		 return None

	 return activation