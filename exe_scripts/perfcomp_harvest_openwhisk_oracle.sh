python3 azure_deploy.py --username yanqi --resource-group harvest-serverless \
    --init-vms --deploy-config perf_comp_harv_openwhisk.json \
    --emul-harvest-trace sim_const_traces \
    --shuffle-invoker-ids \
    --azure-deploy-openwhisk