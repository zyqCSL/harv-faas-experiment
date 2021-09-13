python3 azure_deploy.py --username yanqi --resource-group harvest-serverless \
    --init-vms --deploy-config perf_comp_harv_openwhisk.json \
    --emul-harvest-trace sim_active_traces_padded \
    --shuffle-invoker-ids \
    --azure-deploy-openwhisk