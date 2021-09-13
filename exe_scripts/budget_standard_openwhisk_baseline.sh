python3 azure_deploy.py --username yanqi --resource-group harvest-serverless \
    --init-vms --deploy-config budget_standard.json \
    --emul-harvest-trace sim_trace_standard_base_16 \
    --shuffle-invoker-ids \
    --azure-deploy-openwhisk