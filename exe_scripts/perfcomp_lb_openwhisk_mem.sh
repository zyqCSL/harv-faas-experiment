python3 azure_deploy_vanilla_wsk.py --username yanqi --resource-group harvest-serverless \
    --init-vms --deploy-config perf_comp_harv_openwhisk.json \
    --emul-harvest-trace sim_common_traces_padded \
    --openwhisk-version openwhisk-mem-compare \
    --azure-deploy-openwhisk