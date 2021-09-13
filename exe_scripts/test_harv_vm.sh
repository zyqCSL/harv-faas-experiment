python3 azure_deploy_harvest.py --username yanqi --resource-group harvest-serverless \
    --init-vms --deploy-config test_harvest.json \
    --shuffle-invoker-ids \
    --evict-invoker \
    --azure-deploy-openwhisk