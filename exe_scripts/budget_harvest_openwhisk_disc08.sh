python3 azure_deploy.py --username yanqi --resource-group harvest-serverless \
    --init-vms --deploy-config budget_harv_disc_08.json \
    --emul-harvest-trace sim_trace_harv_disc_08_base_16 \
    --shuffle-invoker-ids \
    --azure-deploy-openwhisk