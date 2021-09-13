python3 azure_deploy.py --username yanqi --resource-group harvest-serverless \
    --init-vms --deploy-config perf_comp_static_openwhisk.json \
    --emul-harvest-trace sim_static_harvdiscount_08_trace \
    --shuffle-invoker-ids \
    --azure-deploy-openwhisk