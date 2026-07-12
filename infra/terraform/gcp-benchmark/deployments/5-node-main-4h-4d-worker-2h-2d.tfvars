deployment_name = "tf-image-pipeline-5node"

main_machine_type   = "e2-standard-8"
worker_machine_type = "e2-standard-4"

main_disk_size_gb   = 350
worker_disk_size_gb = 30

worker_node_count = 4

main_default_workers = 4
main_heavy_workers   = 4

worker_default_workers = 2
worker_heavy_workers   = 2
