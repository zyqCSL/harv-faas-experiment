python3 azure_deploy_vanilla_wsk.py --username yanqi --resource-group harvest-serverless \
    --init-vms --deploy-config perf_comp_harv_openwhisk.json \
    --emul-harvest-trace sim_active_traces_padded \
    --azure-deploy-openwhisk