#!/usr/bin/env python3

import argparse
import gzip
import logging
import os
import re
import shutil
import subprocess
import tempfile

from datetime import datetime
from pathlib import PurePath

import yaml


# FIXME: Make a list if command line arguments which should
# be obfuscated when logging. Don't leak secrets in logs!
SECRET_ARGS = [
  '--s3-access-key-id',
  '--s3-secret-access-key',
  ]


def clean_args(args):
  '''
  Hide sensitive information in command arguments list
  '''

  # If we find a sensitve argument in the list
  # Replace the following entry in the list
  # That must be the secret
  for s in SECRET_ARGS:
    try:
      args[args.index(s)+1] = '******'
    except:
      pass

  # Return object with no sensitive information
  return args


# Valid types
TYPES = {
  'source': ['mysql'],
  'destination': ['s3', 'local']
  }

# Backup names can only have word characters and '-'
re_backup_name = re.compile("^[\w-]+$")


# FLAGS #

parser = argparse.ArgumentParser(
  description='Database backups. Supply a config file with backups to perform.'
  )

parser.add_argument(
    '--config',
    required=False,
    help=('Configuration file'),
    default='/etc/backups.yaml'
    )

parser.add_argument(
    '--log-file',
    required=False,
    help=('Log file')
    )

# Parse the command line arguments
args = parser.parse_args()


# LOAD CONFIG #

# Load configuration file
try:
  stream = open(args.config, 'r')
except FileNotFoundError:
  logging.error("Configuration file '{}' was not found. Use flag '--config FILE' to override default config file path.".format(args.config))
  exit(1)

# Parse the config file
try:
  config = yaml.safe_load(stream)
except yaml.YAMLError as e:
  logging.error("Could not parse configuration file: %s", e)
  exit(1)


# LOGGING #

# Log to stdout
logging_handlers = [logging.StreamHandler()]

# Add logging to file if flag is set
if args.log_file:
  logging_handlers.append(logging.FileHandler(args.log_file))

# Configure logging
logging.basicConfig(
  format='%(asctime)s:%(levelname)s:%(message)s',
  level=eval("logging.{}".format(config.get('loglevel', "INFO").upper())),
  handlers=logging_handlers
  )

# Dir to store local temporary backups
BACKUP_DIR = '/tmp'

try:
  # Default timeout when dumping database
  config['timeout']

  # This is dir on the remote where backups will be stored
  config['rootdir']

except KeyError as e:
  logging.error("Missing key %s in config", e)
  exit(1)


# Run through the backups to perform
for b_name, b_conf in config['backups'].items():
  
  # DUMP DATABASE #

  # Abort on invalid backup name
  if not re_backup_name.match(b_name):
    logging.error("Invalid backup name '%s'", b_name)
    continue

  try:
    # Source config
    s = b_conf['source']

    # Destination config
    d = b_conf['destination']

    # Check source type
    if s['type'] not in TYPES['source']:
      logging.error("%s: Unknown source type '%s'", b_name, s['type'])
      continue
  
    # check destination type
    if d['type'] not in TYPES['destination']:
      logging.error("%s: Unknown destination type '%s'", b_name, d['type'])
      continue

    # Base arguments to pass to mysqldump
    # FIXME: Support compression
    # FIXME: Support option quick
    # FIXME: Support option lock-tables
    args = [
      'mysqldump',
      '--host={}'.format(s['host']),
      '--port={}'.format(s.get('port', 3306)), # Defaults to 3306
      '--user={}'.format(s['user']),
      ]

    # A temp file for storing the password to use for database access
    # This way, we can't leak it in the logs, and we get no warning
    # about using passwords on the command line
    my_conf = tempfile.NamedTemporaryFile()

    if 'password' in s:

      # Write password to file
      my_conf.write(
        "[mysqldump]\npassword={}".format(s['password']).encode("utf-8")
        )

      # Point to beginning of file so mysqldump can read the whole file
      my_conf.seek(0)

      # Make mysqldump read the config file
      args.insert(1, '--defaults-file={}'.format(my_conf.name))

    else:
      # Make it clear that no password is to be used
      # Adding this will warn me of using password on the command line??
      #args.append('--skip-password')
      pass

  except KeyError as e:
    logging.error("%s: Skipping because of missing key '%s' in source config", b_name, e)
    continue


  # Run through databases to back up
  for db in s['databases']:
    # The official time for this backup
    b_datetime = datetime.now()

    # Full path to the temporary local backup
    path_temp = PurePath(
      BACKUP_DIR,
      "{}_{}.sql.gz".format(db, b_datetime.isoformat())
      )

    # Store raw database dump here
    db_raw = tempfile.NamedTemporaryFile()

    # Store compressed database here
    db_gzip = tempfile.NamedTemporaryFile()

    # Dump database to the temp file
    try:
      r = subprocess.run(
        args + [db],
        stdout=db_raw, 
        check=True, # Throw exception on non 0 exit code
        timeout=config['timeout']
        )
      logging.debug("%s: %s", b_name, r)

    except subprocess.CalledProcessError as e:
      logging.error("%s: %s", b_name, e)
      continue

    # Compress database dump
    try:
      with open(db_raw.name, 'rb') as f_in:
        with gzip.open(db_gzip.name, 'wb') as f_out:
          shutil.copyfileobj(f_in, f_out)
    except Exception as e:
      logging.error("%s: When compressing the database file: %s", b_name, e)
      continue
    finally:
      # Remove temp file
      db_raw.close()

    # BACKUP #

    try:

      if d['type'] == 'local':

        path_dest = PurePath(
          d['path'],
          config['rootdir'],
          b_name,
          str(b_datetime.year),
          str(b_datetime.month),
          path_temp.name)
  
        commands = [
          # Make the destination dir
          ["mkdir", "-p", path_dest.parent],
          # Copy the temp file to destination dir
          ["cp", db_gzip.name, path_dest]
          ]

      elif d['type'] == 's3':
        
        # Full path to the file on S3
        path_dest = PurePath(
          "s3:",
          d.get('bucket',os.getenv('S3_BUCKET')),
          config['rootdir'],
          b_name,
          str(b_datetime.year),
          str(b_datetime.month),
          path_temp.name # File name temp file
          )
  
        # rclone base args. Credentials from env if not in config
        rc_args = [
          'rclone',
          '--config', config['rclone_config'],
          '--s3-endpoint', d.get('endpoint', os.getenv('S3_ENDPOINT')),
          '--s3-access-key-id', d.get('access_key_id', os.getenv('S3_ACCESS_KEY_ID')),
          '--s3-secret-access-key', d.get('secret_access_key', os.getenv('S3_SECRET_ACCESS_KEY'))
          ]
  
        # FIXME: If debug, print out rclone version
        # rc_args + ['version']
        # rc_args + ['ls', s3_path]
        # rc_args + ['size', s3_path]

        # Bild commands to perform
        commands = [
          # Make the destination dir (It may not exist)
          rc_args + ['mkdir', path_dest.parent],
          # Copy the file to S3
          rc_args + ['copy', db_gzip.name, path_dest]
          ]

    except KeyError as e:
      logging.error("%s: Skipping because of missing key %s in destination config", b_name, e)
      # FIXME: Delete db dump
      continue

    # Perform backup commands
    try:
      # FIXME: Add dry-run option in config
      for c in commands:
        # FIXME: Add timeout?
        r = subprocess.run(c, check=True)
        logging.debug("%s: %s", b_name, clean_args(r.args))

    except subprocess.CalledProcessError as e:
      logging.error("%s: %s", b_name, clean_args(e.cmd))
      # FIXME: Delete db dump?
    else:
      logging.info("%s: Backed up database '%s' from host '%s' to %s", b_name, db, s['host'], path_dest)
    finally:
      # Close the temp backup file
      db_gzip.close()

  # Close the temporary mysql config file with password
  my_conf.close()
