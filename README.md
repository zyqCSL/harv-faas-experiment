# Faster and Cheaper Serverless Computing on Harvested Resources

This repository contains the codes of real system experiments in the SOSP'21 paper "<strong>Faster and Cheaper Serverless Computing on Harvested Resources</strong>", and specifically, it contains the codes to deploy OpenWhisk on Azure and to run experiments. The codes of modified versions of OpenWhisk are in <https://github.com/zyqCSL/openwhisk_archive>, and the benchmarks are in <https://github.com/zyqCSL/openwhisk_workloads>.

There is also another repository for the paper, which contains the analysis codes and an anonymized subset of the traces <>.

## Prerequisites

- Install & set up Azure CLI (<https://docs.microsoft.com/en-us/cli/azure/install-azure-cli>).

- Python 3.6+

## Repository structure

- `azure_deploy_*` creates Azure VMs, deploys OpenWhisk and sets up MinIO and benchmark

- `azure_autoscale_*` is the control plane of real Harvest and Spot VM experiments. It keeps track of the total CPU number in the cluster, and creates new VMs to make up for the lost CPUs due to VM eviction and shrinkage.

- `config` contains files of the cluster and OpenWhisk deployment

- `misc` contains scripts to generate config files

- `exp_scripts` contains scripts for deploying OpenWhisk Azure

- `src` utilization functions

- `scripts` initialization scripts for Azure VMs

## Usage

Before running the deployment scripts, please make sure to specify Azure username with `--username` and to change the resource group.

### Comparison of load balancing algorithms

This set of experiments compare the performance of different load balancing algorithms ( *Min-worker-set*, *Join-the-shortest queue* and *Vanilla OpenWhisk*)

To create VMs and deploy OpenWhisk, run one of the following scripts, corresponding to the tested load balancing algorithm.

*Min-worker-set*:

```bash
./exe_scripts/perfcomp_lb_openwhisk.sh
```

*Join-the-shortest-queue*:

```bash
./exe_scripts/perfcomp_lb_openwhisk_jsq.sh           
```

*Vanilla OpenWhisk*:

```bash
./exe_scripts/perfcomp_lb_openwhisk_mem.sh
```

To run the performance experimence, log into the host node (specified as `host_node` in the json configuration file in `config` and ususally `node-0`), with the ssh keys saved in directory `keys` (ssh -i keys/id_rsa USER@IP). IP of the host node (and all other nodes) can be found in `logs/external_ip.json`. . You can change the experiment time of each concurrent user number with `--exp-time` argument, and change tested number of concurrent users by changing the `users` loop in the `run_locust_loop.py` script.

When the experiments complete, invoker CPU usage data is saved in `invoker_logs_users_N`, and invocation latency data is saved in `openwhisk_locust_log_users_N`, both on the host node.

For *Min-worker-set* (*MWS*), run

```bash
python3 run_locust_loop.py --invoker-ips invoker_ips.json --exp-time 20m
```

For *Join-the-shortest-queue* (*JSQ*), run

```bash
python3 run_locust_loop.py --invoker-ips invoker_ips.json --exp-time 20m --openwhisk-version openwhisk-harv-vm-cgroup-azure-distributed-jsq
```

For *Vanilla OpenWhisk*, run

```bash
python3 run_locust_loop_mem_compare.py --invoker-ips invoker_ips.json --exp-time 20m --use-server-cgroup
```

### Emulating Harvest VM variation

This set of experiments compares performance of MWS under VM traces with different variation frequency through emulation.

Deploy *MWS* on *Harvest VMs* with active CPU variation:

```bash
./exe_scripts/perfcomp_harvest_openwhisk_active.sh
```

Deploy *MWS* on *Harvest VMs* with normal CPU variation:

```bash
./exe_scripts/perfcomp_harvest_openwhisk_common.sh
```

Deploy *MWS* on dedicated *Regular VMs*:

```bash
./exe_scripts/perfcomp_harvest_openwhisk_oracle.sh
```

Deploy *Vanilla OpenWhisk* on *Harvest VMs* with active CPU variation:

```bash
./exe_scripts/perfcomp_vanilla_wsk_active.sh
```

Deploy *Vanilla OpenWhisk* on dedicated *Regular VMs*

```bash
./exe_scripts/perfcomp_vanilla_wsk_oracle.sh
```

Instructions for running experiments are the same for *MWS* and *Vanilla OpenWhisk* as in the pervious section.

### Impact of discount ratio with the same budget

This set of experiments compare the performance of *MWS* on *Harvest VMs* with different different discount ratio for evictable CPUs and harvested CPUs, and the same budget. The following scripts deploy the cluster to test the *Baseline*, *Lowest*, *Typical*, *Highest* and *Best* configurations as described in the paper. Instructions for running experiments are the same as *MWS* in pervious section.

```bash
./exe_scripts/budget_standard_openwhisk_baseline.sh
./exe_scripts/budget_harvest_openwhisk_evict_disc048.sh
./exe_scripts/budget_harvest_openwhisk_disc08.sh
./exe_scripts/budget_harvest_openwhisk_disc09.sh
./exe_scripts/budget_harvest_openwhisk_evict_disc088.sh
```

### Harvest VMs vs. Spot VMs

This set of experiments compare the performance of *Harvest VMs* and *Spot VMs* with a synthetic trace snapshot of Azure Function workload.

Run one of the following scripts to create VMs and deploy OpenWhisk.

Deploy *Vanilla OpenWhisk* on *Regular VMs*

```bash
./exe_scripts/test_harv_vm_synthetic_baseline.sh
```

Deploy *MWS* on real *Harvest VMs*

```bash
./exe_scripts/test_harv_vm_synthetic.sh
```

Deploy *MWS* on real *Spot VMs* with 4 and 48 CPUs.

```bash
./exe_scripts/test_spot_s4.sh
./exe_scripts/test_spot_s48.sh
```

For *Harvest VM* and *Spot VM* experiments, a resource monitor is needed to keep track of the total CPUs in the cluster, and to create new VMs to make up for the lost CPUs due to VM eviction or shrinkage.

For *Harvest VM*, run the resource monitor with:

```bash
./exe_scripts/auto_scale_harv_vm.sh
```

For *Spot VM*, run the resource monitor with one of the following according to VM size:

```bash
./exe_scripts/auto_scale_spot_s4.sh
./exe_scripts/auto_scale_spot_s48.sh
```

You can also change the experiment time, monitoring interval, and total number of CPUs by changing the `--exp-time`, `--check-interval` and `--req-cluster-vcpus` arguments in the script.

To run experiments, first log into the `host_node` VM (specified as non-evictable). To start the experiemnts for *MWS*, run:

```bash
python3 run_harv_synthetic.py --exp-time 130m --interval 30s --invoker-ips invoker_ips.json --func-trace func_trace_synthetic.json
```

And for *Vanilla OpenWhisk*, run:

```bash
python3 run_harv_synthetic.py --exp-time 130m --interval 30s --invoker-ips invoker_ips.json --func-trace func_trace_synthetic.json --openwhisk-version openwhisk-mem-compare
```

When the experiments complete, invoker CPU usage data is saved in `invoker_logs`, and invocation latency data is saved in `synthetic_activation_log`, both on the host node.
