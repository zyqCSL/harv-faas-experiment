import json
import logging
import sys
import subprocess
from pathlib import Path

def generate_hosts(controller_vm_ips, invoker_vm_ips, 
            host_ip, config_dir):
    # require one vm for each invoker
    # controller can share the same vms)
    with open(str(config_dir / 'hosts.j2.ini'), 'w+') as f:
        f.write('; the first parameter in a host is the inventory_hostname\n\n' + \
            '; used for local actions only\n' + \
            'ansible ansible_connection=local\n')
        # edge
        f.write('\n[edge]\n')
        f.write('%s          ansible_host=%s ansible_connection=ssh\n' %(
            host_ip, host_ip))
        
        # controllers
        f.write('\n[controllers]\n')
        for controller in controller_vm_ips:
            assert int(controller.split('controller')[1]) >= 0
            f.write('%s         ansible_host=%s ansible_connection=ssh\n' %(
                controller, controller_vm_ips[controller]))
        
        # kafkas
        f.write('\n[kafkas]\n')
        f.write('kafka0              ansible_host=%s ansible_connection=ssh\n' %host_ip)

        # zookeepers
        f.write('\n[zookeepers:children]\nkafkas\n')

        # invokers
        f.write('\n[invokers]\n')
        for invoker in invoker_vm_ips:
            assert int(invoker.split('invoker')[1]) >= 0
            f.write('%s            ansible_host=%s ansible_connection=ssh\n' %(
                invoker, invoker_vm_ips[invoker]))
        
        # db
        f.write('\n[db]\n')
        f.write('%s              ansible_host=%s ansible_connection=ssh\n' %(
            host_ip, host_ip))
        
        # redis
        f.write('\n[redis]\n')
        f.write('%s              ansible_host=%s ansible_connection=ssh\n' %(
            host_ip, host_ip))
        
        # apigateway
        f.write('\n[apigateway]\n')
        f.write('%s              ansible_host=%s ansible_connection=ssh\n' %(
            host_ip, host_ip))

# generate the hosts file for adding new invokers to deployed openwhisk
def generate_hosts_new_invokers(controller_vm_ips, 
            invoker_vm_ips, new_invoker_vm_ips,
            host_ip, config_dir):
    # require one vm for each invoker
    # controller can share the same vm
    with open(str(config_dir / 'hosts.j2.ini'), 'w+') as f:
        f.write('; the first parameter in a host is the inventory_hostname\n\n' + \
            '; used for local actions only\n' + \
            'ansible ansible_connection=local\n')
        # edge
        f.write('\n[edge]\n')
        f.write('%s          ansible_host=%s ansible_connection=ssh\n' %(
            host_ip, host_ip))
        
        # controllers
        f.write('\n[controllers]\n')
        for controller in controller_vm_ips:
            assert int(controller.split('controller')[1]) >= 0
            f.write('%s         ansible_host=%s ansible_connection=ssh\n' %(
                controller, controller_vm_ips[controller]))
        
        # kafkas
        f.write('\n[kafkas]\n')
        f.write('kafka0              ansible_host=%s ansible_connection=ssh\n' %host_ip)

        # zookeepers
        f.write('\n[zookeepers:children]\nkafkas\n')

        # invokers
        f.write('\n[invokers]\n')
        for invoker in invoker_vm_ips:
            assert int(invoker.split('invoker')[1]) >= 0
            f.write('%s            ansible_host=%s ansible_connection=ssh\n' %(
                invoker, invoker_vm_ips[invoker]))
        
        # new invokers
        f.write('\n[new_invokers]\n')
        for invoker in new_invoker_vm_ips:
            assert int(invoker.split('invoker')[1]) >= 0
            f.write('%s            ansible_host=%s ansible_connection=ssh\n' %(
                invoker, new_invoker_vm_ips[invoker]))
        
        # db
        f.write('\n[db]\n')
        f.write('%s              ansible_host=%s ansible_connection=ssh\n' %(
            host_ip, host_ip))
        
        # redis
        f.write('\n[redis]\n')
        f.write('%s              ansible_host=%s ansible_connection=ssh\n' %(
            host_ip, host_ip))
        
        # apigateway
        f.write('\n[apigateway]\n')
        f.write('%s              ansible_host=%s ansible_connection=ssh\n' %(
            host_ip, host_ip))


# generate invoker.yml, to be saved in $openwhisk/ansible
def generate_invoker_yml(config_dir, invoker_ids):
    with open(str(config_dir / 'invoker.yml'), 'w+') as f:
        f.write('---\n')
        f.write('# This playbook deploys Openwhisk Invokers.\n\n')

        f.write('- hosts: invokers\n')
        f.write('  vars:\n')

        comment = '    #\n' + \
            '    # host_group - usually \"{{ groups[\'...\'] }}\" where \'...\' is what was used\n' + \
            '    #   for \'hosts\' above.  The hostname of each host will be looked up in this\n' + \
            '    #   group to assign a zero-based index.  That index will be used in concert\n' + \
            '    #   with \'name_prefix\' below to assign a host/container name.\n'
        f.write(comment)
        f.write('    host_group: \"{{ groups[\'invokers\'] }}\"\n')

        comment = '    #\n' + \
            '    # name_prefix - a unique prefix for this set of invokers.  The prefix\n' + \
            '    #   will be used in combination with an index (determined using\n' + \
            '    #   \'host_group\' above) to name host/invokers.\n'
        f.write(comment)
        f.write('    name_prefix: \"invoker\"\n')

        comment = '    #\n' + \
            '    # invoker_ids: the exact id of each invoker, and each invoker will names names as {name_prefix}{invoker_id}\n'
        f.write(comment)
        f.write('    invoker_ids:\n')
        for invoker_id in invoker_ids:
            f.write('      - ' + str(invoker_id) + '\n')

        f.write('\n  roles:\n')
        f.write('    - invoker\n')


# generate new_invoker.yml, to be saved in $openwhisk/ansible
# used for adding new invokers in real time to deployed openwhisk
# in order to replace failed invokers. 
# new_invoker_ids should be in the same order as new_invokers group in hosts file
def generate_new_invoker_yml(config_dir, new_invoker_ids):
    with open(str(config_dir / 'new_invoker.yml'), 'w+') as f:
        f.write('---\n')
        f.write('# This playbook deploys Openwhisk Invokers.\n\n')

        f.write('- hosts: new_invokers\n')
        f.write('  vars:\n')

        comment = '    #\n' + \
            '    # host_group - usually \"{{ groups[\'...\'] }}\" where \'...\' is what was used\n' + \
            '    #   for \'hosts\' above.  The hostname of each host will be looked up in this\n' + \
            '    #   group to assign a zero-based index.  That index will be used in concert\n' + \
            '    #   with \'name_prefix\' below to assign a host/container name.\n'
        f.write(comment)
        f.write('    host_group: \"{{ groups[\'new_invokers\'] }}\"\n')

        comment = '    #\n' + \
            '    # name_prefix - a unique prefix for this set of invokers.  The prefix\n' + \
            '    #   will be used in combination with an index (determined using\n' + \
            '    #   \'host_group\' above) to name host/invokers.\n'
        f.write(comment)
        f.write('    name_prefix: \"invoker\"\n')

        comment = '    #\n' + \
            '    # new_invoker_ids: the exact id of each invoker, and each invoker will names names as {name_prefix}{invoker_id}\n'
        f.write(comment)
        f.write('    new_invoker_ids:\n')
        for invoker_id in new_invoker_ids:
            f.write('      - ' + str(invoker_id) + '\n')

        f.write('\n  roles:\n')
        f.write('    - new_invoker\n')
        

def generate_couchdb_setup(config_dir, couchdb_ip, username):
    with open(str(config_dir / 'setup_couchdb.sh'), 'w+') as f:
        f.write('export OW_DB=CouchDB\n')
        f.write('export OW_DB_USERNAME=%s\n' %username)
        f.write('export OW_DB_PASSWORD=openwhisk_couch\n')
        f.write('export OW_DB_PROTOCOL=http\n')
        f.write('export OW_DB_HOST=%s\n' %couchdb_ip)
        f.write('export OW_DB_PORT=5984\n')
        f.write('ansible-playbook setup.yml')
    cmd = 'chmod +x %s' %(str(config_dir / 'setup_couchdb.sh')) 
    subprocess.run(cmd, shell=True)


def generate_setup_add_invoker(config_dir, couchdb_ip, username):
    with open(str(config_dir / 'setup_add_invoker.sh'), 'w+') as f:
        f.write('export OW_DB=CouchDB\n')
        f.write('export OW_DB_USERNAME=%s\n' %username)
        f.write('export OW_DB_PASSWORD=openwhisk_couch\n')
        f.write('export OW_DB_PROTOCOL=http\n')
        f.write('export OW_DB_HOST=%s\n' %couchdb_ip)
        f.write('export OW_DB_PORT=5984\n')
        f.write('ansible-playbook setup_invoker.yml')
    cmd = 'chmod +x %s' %(str(config_dir / 'setup_add_invoker.sh')) 
    subprocess.run(cmd, shell=True)
