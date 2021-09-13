python3 azure_deploy_spot_synthetic.py --username yanqi --resource-group harvest-serverless \
    --init-vms --deploy-config test_spot_s2.json \
    --shuffle-invoker-ids \
    --azure-deploy-openwhisk