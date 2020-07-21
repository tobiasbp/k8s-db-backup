FROM python:3-alpine

# Install needed software
RUN apk add --no-cache rclone mysql-client

# Add the backup script
COPY src/do-db-backup.py /usr/local/bin/
# Make it executable
#RUN chmod +x /usr/local/bin/do-db-backup.py

# Backups configuration
COPY src/backups.yaml /etc/backups/
#RUN chmod 600 /etc/backups.yaml

# Rclone needs a section for each backend 
COPY src/rclone.conf /etc/

# Install Python packages
COPY src/requirements.txt .
RUN pip install --requirement requirements.txt

# Make a dir for storing backups
RUN mkdir /var/log/backups

# Do a backup
ENTRYPOINT [ "python", "/usr/local/bin/do-db-backup.py", "--log-file", "/var/log/backups/backups.log","--config", "/etc/backups/backups.yaml"]
