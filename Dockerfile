FROM python:3-alpine

# Install needed software
RUN apk add --no-cache rclone mysql-client

# Add the backup script
COPY src/do-db-backup.py /usr/local/bin/
# Make it executable
#RUN chmod +x /usr/local/bin/do-db-backup.py

# Backups configuration
COPY src/backups.yaml /etc/
#RUN chmod 600 /etc/backups.yaml

# Install Python packages
COPY src/requirements.txt .
RUN pip install --requirement requirements.txt

# Do a backup
ENTRYPOINT [ "python", "/usr/local/bin/do-db-backup.py"]
