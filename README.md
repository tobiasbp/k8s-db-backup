# k8s-db-backup
A Docker image backup up databases. To be run as a cron job in Kubernetes 

Dumps data with _mysqldump_ and uploads to _S3_ using _rclone_.


# To do
- [ ] Read all backup config files in config dir.
- [ ] Add other rclone backends by looking at (documentet config)[https://rclone.org/s3/#wasabi]
- [ ] Setting for mac number of backups? Max age?
