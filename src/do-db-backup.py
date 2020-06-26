#!/usr/bin/env python3

from datetime import datetime
import subprocess

#import tempfile
#import gzip


import yaml

# Sources definition
sources = {
  'mysql': {
    'databases': [],
    'host': None,
    'password': None,
    'port': '3306',
    'user': None
    },
  }

destinations = {
  's3': {
    'acces_key_id': None,
    'bucket': None,
    'endpoint': None,
    'secret_access_key': None,
    'region': None
    },
  'local': {
    'path': None
    }
  }


# Dir to store backups
BACKUP_DIR = '/tmp'

# Default timeout when dumping database
DUMP_TIMEOUT = 60

# This is dir on the remote where backups will be stored
TOP_DIR = 'backups'

# Load configuration of backups
stream = open('./backups.yaml', 'r')
backups = yaml.safe_load(stream)

# FIXME: Define valid configs as dicts


for b_name, b_conf in backups.items():
  print(b_name)
  
  
  # Defaults for this type
  #d = sources[s['type']]
  #print(d)
  
  #print("Source:", b_conf['source'])
  #print("Destination:", b_conf['destination'])

  # FIXME: Validate config
  try:
    # Source config
    s = b_conf['source']

    # Destination config
    d = b_conf['destination']

    # The arguments to pass to mysqldump
    args = [
      'mysqldump',
      '--host=' + s['host'],
      # Default port if not defined
      '--port=' + str(s.get('port', sources[s['type']]['port'])),
      '--user=' + str(s['user']),
      '--password=' + str(s['password']),
      '--databases'
      ]
    # List of databases to back up
    dbs = s['databases']

  except KeyError as e:
    print("Skipping '{}' because of missing key {} in source config"
      .format(b_name, e))
    continue

  # Run through databases to back up
  for db in dbs:
    # The official time for this backup
    b_datetime = datetime.now()
    
    # Name of backup file
    file_name =  "{}_{}.sql.gz".format(
      db, b_datetime.isoformat() 
      )

    # Full path to backup file
    file_path = "{}/{}".format(BACKUP_DIR, file_name)
    
    # Create backup file
    out_file = open(file_path, '+w')

    # Dump database to a pipe
    p_dump = subprocess.Popen(
      args + [db],
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      universal_newlines=True,
      )

    # Compress data from pipe to file
    p_comp = subprocess.Popen(
      ['gzip'],
      stdin=p_dump.stdout,
      stdout=out_file,
      )

    # Wait for pipe to complete
    try:
      comp_stdout, comp_stderr = p_comp.communicate(timeout=DUMP_TIMEOUT)
      dump_stdout, dump_stderr = p_dump.communicate(timeout=DUMP_TIMEOUT)
    except subprocess.TimeoutExpired as e:
      # FIXME: Are these not killed automatically on timeout? Only the one which crashed. What about the other?
      p_comp.kill()
      p_dump.kill()
      print("{}".format(e))
      continue
    finally:
      # Close backup file
      out_file.close()
      

    if p_dump.returncode != 0 or p_comp.returncode != 0:
      print("Could not dump database {} from host {}".format(db, b_conf['source'].get('host')))
      #print("stderr: {}".format(d_stderr))
      print(dump_stderr)
      print(comp_stderr)
    else:
      print("Dumped database '{}' from host '{}' to local file '{}'".format(db, b_conf['source'].get('host'), file_name))  


    ###################
    # TRANSFER BACKUP #
    ###################
    if d['type'] == 's3':
      
      try:
        # Args to pass to rclone
        #print(d)
        rc_args = [
          'rclone',
          '--config', 'rclone.conf',
          '--s3-endpoint', d['endpoint'],
          '--s3-access-key-id', d['access_key_id'],
          '--s3-secret-access-key', d['secret_access_key']
          ]
        # This is the path on the remote where the file will be stored
        # FIXME: these could have / in them check
        # FIXME: Use path library
        s3_path = "s3:/{}/{}/{}/{}/{}/".format(
          d['bucket'],
          TOP_DIR,
          b_name,
          b_datetime.year,
          b_datetime.month,
          )

        #print(s3_path)
      except KeyError as e:
        print("Skipping '{}' because of missing key {} in destination config"
          .format(b_name, e))
        # FIXME: Delete db dump
        continue
      
    
      #print(rc_args)
      try:
        # FIXME: These could be looped
        a_mkdir = rc_args + ['mkdir', s3_path]
        a_ls = rc_args + ['ls', s3_path]
        a_size = rc_args + ['size', s3_path]
        a_version = rc_args + ['version']
        
        #a_move = rc_args + ['--dry-run', '--progress', 'move', file_path, s3_path]
        #a_move = rc_args + ['--progress', 'move', file_path, s3_path]
        a_move = rc_args + ['move', file_path, s3_path]
        
        
        #subprocess.run(a_version, check=True)
        
        subprocess.run(a_mkdir, check=True)
        
        subprocess.run(a_move, check=True)
        
        #subprocess.run(a_ls, check=True)
        
        #subprocess.run(a_size, check=True)
        
        
      except subprocess.CalledProcessError as e:
        #print("Error:", e)
        print(e)
        # FIXME: Delete db dump?
      else:
        print("Backed up to: {}{}".format(s3_path, file_name))

