python3 azure_deploy.py --username yanqi --resource-group harvest-serverless \
    --init-vms --deploy-config budget_harv_evict_disc_048.json \
    --emul-harvest-trace sim_trace_evict_disc_048_base_16 \
    --shuffle-invoker-ids \
    --azure-deploy-openwhisk