python3 azure_autoscale.py --shuffle-invoker-ids \
    --deploy-config test_harvest.json \
    --evict-invoker \
    --exp-time 7200 \
    --check-interval 30 \
    --req-cluster-vcpus 150