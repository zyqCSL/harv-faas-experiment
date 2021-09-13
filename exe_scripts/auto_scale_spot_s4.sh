python3 azure_autoscale_spot.py --shuffle-invoker-ids \
    --deploy-config test_spot_s4.json \
    --vm-size s4 \
    --evict-invoker \
    --exp-time 7200 \
    --check-interval 30 \
    --req-cluster-vcpus 150