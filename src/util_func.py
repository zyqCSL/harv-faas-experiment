import sys
import subprocess

def scp(source, target, identity_file, quiet=False, timeout=None):
    _stdout = sys.stdout
    _stderr = sys.stderr
    if quiet:
        _stdout = subprocess.DEVNULL
        _stderr = subprocess.DEVNULL
    if timeout == None:
        cmd = 'scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ' + \
            '-i ' + str(identity_file) + ' ' + str(source) + ' ' + str(target)
    else:
        cmd = 'scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ' + \
            '-o ConnectTimeout=' + str(int(timeout)) + ' ' + \
            '-i ' + str(identity_file) + ' ' + str(source) + ' ' + str(target)
    subprocess.run(cmd, shell=True, stdout=_stdout, stderr=_stderr)

def rsync(source, target, identity_file, quiet=False):
    _stdout = sys.stdout
    _stderr = sys.stderr
    if quiet:
        _stdout = subprocess.DEVNULL
        _stderr = subprocess.DEVNULL
    cmd = 'rsync -arz --info=progress2 -e ' + \
        '\"ssh -q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ' + \
        '-i ' + str(identity_file) + '\" ' + \
        str(source) + ' ' + str(target)
    subprocess.run(cmd, shell=True, stdout=_stdout, stderr=_stderr)

def ssh(destination, cmd, identity_file, quiet=False, timeout=None):
    _stdout = sys.stdout
    _stderr = sys.stderr
    if quiet:
        _stdout = subprocess.DEVNULL
        _stderr = subprocess.DEVNULL
    if timeout == None:
        cmd = 'ssh -q -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' + \
            '-i ' + str(identity_file) + ' ' + \
            str(destination) + ' \"' + cmd + '\"'
    else:
        cmd = 'ssh -q -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' + \
            '-o ConnectTimeout=' + str(int(timeout)) + ' ' + \
            '-i ' + str(identity_file) + ' ' + \
            str(destination) + ' \"' + cmd + '\"'
    if not quiet:
        print("ssh cmd = " + cmd)
    subprocess.run(cmd, shell=True, stdout=_stdout, stderr=_stderr)

def ssh_checkoutput(destination, cmd, identity_file, quiet=False, timeout=None):
    _stderr = sys.stderr
    if quiet:
        _stderr = subprocess.DEVNULL
    
    if timeout == None:
        cmd = 'ssh -q -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' + \
            '-i ' + str(identity_file) + ' ' + \
            str(destination) + ' \"' + cmd + '\"'
    else:
        cmd = 'ssh -q -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' + \
            '-o ConnectTimeout=' + str(int(timeout)) + ' ' + \
            '-i ' + str(identity_file) + ' ' + \
            str(destination) + ' \"' + cmd + '\"'

    if not quiet:
        print("ssh cmd = " + cmd)
    try:
        return subprocess.check_output(cmd, shell=True, stderr=_stderr)
    except subprocess.CalledProcessError as e:
        print(e.output)
        return None