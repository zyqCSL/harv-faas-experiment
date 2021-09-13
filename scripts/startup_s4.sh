#!/bin/bash

apt-get remove docker docker-engine docker.io containerd runc
# install docker-ce, pull images
apt-get -y update
apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get -y update
apt-get -y install docker-ce docker-ce-cli containerd.io

# docker-compose
curl -L "https://github.com/docker/compose/releases/download/1.27.4/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

service docker restart
usermod -aG docker yanqi
# docker pull yanqi/social-network-ml-swarm:latest --quiet

# cgroup & sysstat
apt-get -y --no-install-recommends install \
  cgroup-tools \
  sysstat
cgcreate -g memory,cpu:cgroup_harvest_vm
echo 100000 > /sys/fs/cgroup/cpu/cgroup_harvest_vm/cpu.cfs_period_us
# assume 48 cores, to be changed later
echo 200000 > /sys/fs/cgroup/cpu/cgroup_harvest_vm/cpu.cfs_quota_us
chmod 777 /sys/fs/cgroup/cpu/cgroup_harvest_vm/cpu.cfs_period_us
chmod 777 /sys/fs/cgroup/cpu/cgroup_harvest_vm/cpu.cfs_quota_us


# python packages
apt-get -y --no-install-recommends install \
  python \
  python-pip \
  python-setuptools \
  python3 \
  python3-pip \
  python3-setuptools \
  zip \
  unzip

pip install argcomplete
pip install couchdb

# pip install ansible==2.5.2 \
#   jinja2==2.9.6

# ansible
pip install --upgrade setuptools pip
apt-get install -y software-properties-common
apt-add-repository -y ppa:ansible/ansible
apt-get update
apt-get install -y python-dev libffi-dev libssl-dev
pip install markupsafe
pip install ansible==2.5.2
pip install jinja2==2.9.6
pip install docker==2.2.1    --ignore-installed  --force-reinstall
pip install httplib2==0.9.2  --ignore-installed  --force-reinstall
pip install requests==2.10.0 --ignore-installed  --force-reinstall

# # prereq
# pip install docker==4.0.2

pip3 install argparse \
  minio \
  numpy \
  requests-futures
# pip3 install argparse \
#   pandas \
#   numpy \
#   docker \
#   pyyaml \
#   aiohttp \
#   asyncio

apt-get install -y nodejs
apt-get install -y npm

# Java
JAVA_SOURCE=${1:-"open"}

if [ "$JAVA_SOURCE" != "oracle" ] ; then
    if [ "$(lsb_release -cs)" == "trusty" ]; then
        apt-get install -y software-properties-common python-software-properties
        add-apt-repository ppa:jonathonf/openjdk -y
        apt-get update
    fi

    apt-get install openjdk-8-jdk -y
else
    apt-get install -y software-properties-common python-software-properties
    add-apt-repository ppa:webupd8team/java -y
    apt-get update

    echo 'oracle-java8-installer shared/accepted-oracle-license-v1-1 boolean true' | debconf-set-selections
    apt-get install oracle-java8-installer -y
fi

# # pre-requirements for wrk2
# apt-get -y --no-install-recommends install libssl-dev \
#   libz-dev \
#   luarocks \
#   gcc
# luarocks install luasocket

# set up .kvp_pool_0 (core number)
touch /var/lib/hyperv/.kvp_pool_0
if [ ! -s /var/lib/hyperv/.kvp_pool_0 ]; then 
    printf "CurrentCoreCount%b%b%b%b4.000%b" "\0" "\0" "\0" "\0" "\0" > /var/lib/hyperv/.kvp_pool_0; 
fi
chmod 777 /var/lib/hyperv/.kvp_pool_0

# set up .kvp_pool_2 (mem in bytes)
touch /var/lib/hyperv/.kvp_pool_2
printf "CurrentMemoryMB%b%b%b%b16384%b" "\0" "\0" "\0" "\0" "\0" > /var/lib/hyperv/.kvp_pool_2
chmod 777 /var/lib/hyperv/.kvp_pool_2

# # git clones
# git clone https://github.com/zyqCSL/sinan-gcp.git /home/yanqi/sinan-gcp
# chown -R yanqi:yanqi /home/yanqi/sinan-gcp
git clone https://github.com/zyqCSL/openwhisk_workloads.git /home/yanqi/openwhisk_workloads
chown -R yanqi:yanqi /home/yanqi/openwhisk_workloads

# for locust
mkdir /home/yanqi/serverless_locust_log
chmod -R 777 /home/yanqi/serverless_locust_log

mkdir /home/yanqi/openwhisk_locust_log
chmod -R 777 /home/yanqi/openwhisk_locust_log

# should be done in ansible in user mode
# # set up metadata service
# curl -H Metadata:true http://169.254.169.254/metadata/scheduledevents?api-version=2019-08-01

# finish flag
touch /home/yanqi/startup_finished
chown yanqi:yanqi /home/yanqi/startup_finished