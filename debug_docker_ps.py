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

username = 'yanqi'
vm_ip = '51.143.90.101'
identity_file = Path.cwd() / 'keys' / 'id_rsa'

cmd = 'docker ps | grep invoker'
timeout = None
quiet = False
if timeout == None:
    r = ssh_checkoutput(destination=username+'@'+vm_ip, 
        cmd=cmd, identity_file=str(identity_file), quiet=quiet)
else:
    left_trials = 3
    while left_trials > 0:
        r = ssh_checkoutput(destination=username+'@'+vm_ip, 
            cmd=cmd, identity_file=str(identity_file), quiet=quiet, timeout=timeout)
        if r != None:
            r = r.decode("utf-8")
            print('after decode')
            print([r])
        else:
            print('None')
        left_trials -= 1
        time.sleep(5)

if r != None:
    r = r.decode("utf-8")
    print('after decode')
    print([r])

    if r.replace(' ', '') == '':
        print('no invoker deployed')
    else:
        print('deployed')
else:
    print('None')