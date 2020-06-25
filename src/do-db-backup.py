#!/usr/bin/env python3

import subprocess
import tempfile
import gzip


import yaml

# Dir to store backups
BACKUP_DIR = '/tmp'

# Default timeout when dumping database
DUMP_TIMEOUT = 60

# Load configuration of backups
stream = open('./backups.yaml', 'r')
backups = yaml.safe_load(stream)

# FIXME: Define valid configs as dicts

# FIXME: Validate config

for b_name, b_conf in backups.items():
  print(b_name)
  print("Source:", b_conf['source'])
  #print("Destination:", b_conf['destination'])

  # The arguments to pass to mysqldump
  args = [
    'mysqldump',
    '--host=' + b_conf['source'].get('host'),
    '--port=' + str(b_conf['source'].get('port')),
    '--user=' + b_conf['source'].get('user'),
    '--password=' + str(b_conf['source'].get('password')),
    '--databases'
    ]

  # Run through databases to back up
  for db in b_conf['source'].get('databases', []):

    # Name of backup file
    file_name =  "{}/{}.sql.gz".format(BACKUP_DIR, db)
    
    # Create backup file
    out_file = open(file_name, '+w')

    # Dump database to a pipe
    p_dump = subprocess.Popen(
      args + [db],
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      universal_newlines=True
      )

    # Compress data from pipe to file
    p_comp = subprocess.Popen(
      ['gzip'],
      stdin=p_dump.stdout,
      stdout=out_file
      )

    # Wait for pipe to complete
    try:
      comp_stdout, comp_stderr = p_comp.communicate(timeout=DUMP_TIMEOUT)
    except subprocess.TimeoutExpired:
      p_comp.kill()
      print("Timeout compress {}".format(file_name))
      out_file.close()
      continue
      
    try:
      dump_stdout, dump_stderr = p_dump.communicate(timeout=DUMP_TIMEOUT)
    except subprocess.TimeoutExpired:
      p_dump.kill()
      print("Timeout dump {}".format(file_name))
      out_file.close()
      continue

    # Close backup file
    out_file.close()

    if p_dump.returncode != 0 or p_comp.returncode != 0:
      print("Could not dump database {} from host {}".format(db, b_conf['source'].get('host')))
      #print("stderr: {}".format(d_stderr))
      print(dump_stderr)
      print(comp_stderr)
    else:
      print("Dumped database {} from host {} to {}".format(db, b_conf['source'].get('host'), file_name))  
