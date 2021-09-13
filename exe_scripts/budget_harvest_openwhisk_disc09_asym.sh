python3 azure_deploy.py --username yanqi --resource-group harvest-serverless \
    --init-vms --deploy-config budget_harv_disc_09.json \
    --emul-harvest-trace sim_trace_harv_disc_09_base_16_asym \
    --shuffle-invoker-ids \
    --azure-deploy-openwhisk
