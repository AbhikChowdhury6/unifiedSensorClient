- copy iso to proxmox
    - scp /home/chowder/Downloads/ubuntu-22.04.5-live-server-amd64.iso root@192.168.20.137:/var/lib/vz/template/iso


to setup vm
- 4 cpu’s
- 8 gigs of ram
- 100 gig HDD
- ubuntu server
    - install with LUKS
- get public key copied (do this in a more secure way)
    - on remote
        - cat ~/.ssh/id_rsa.pub | nc -l -p 9000
    - on VM
        - nc 192.168.20.64 9000 >> ~/.ssh/authorized_keys
        - ctrl+c to exit


## install timescale

sudo mkdir -p /etc/apt/keyrings
wget -qO- https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor | sudo tee /etc/apt/keyrings/timescaledb.gpg > /dev/null

echo "deb [signed-by=/etc/apt/keyrings/timescaledb.gpg] https://packagecloud.io/timescale/timescaledb/ubuntu/ jammy main" | sudo tee /etc/apt/sources.list.d/timescaledb.list

sudo apt update

sudo apt install timescaledb-2-postgresql-17 postgresql-client-17



## create a DB

sudo -u postgres psql

in the psql shell:

CREATE DATABASE sensordb;
\c sensordb
CREATE EXTENSION IF NOT EXISTS timescaledb;

create a user with a password:

CREATE USER sensor_user WITH PASSWORD 'yourpassword';
GRANT ALL PRIVILEGES ON DATABASE sensordb TO sensor_user;

allow remote connections

sudo nano /etc/postgresql/15/main/postgresql.conf
update line to: listen_addresses = '*'

sudo nano /etc/postgresql/17/main/pg_hba.conf
host    sensordb        sensor_user     192.168.201.0/24        md5

sudo systemctl restart postgresql

## Connect to DB

pip install psycopg2-binary sqlalchemy pandas

import psycopg2

conn = psycopg2.connect(
dbname='sensordb',
user='sensor_user',
password='yourpassword',
host='192.168.201.37',  # your Proxmox VM IP
port=5432
)

cur = conn.cursor()

# Create a simple table

cur.execute("""
CREATE TABLE IF NOT EXISTS temperature (
time TIMESTAMPTZ NOT NULL,
device_id TEXT NOT NULL,
value DOUBLE PRECISION NOT NULL
);
SELECT create_hypertable('temperature', 'time', if_not_exists => TRUE);
""")

# Insert

cur.execute("""
INSERT INTO temperature (time, device_id, value)
VALUES (NOW(), 'device01', 23.5);
""")

# Read

cur.execute("SELECT * FROM temperature;")
print(cur.fetchall())

# Update

cur.execute("""
UPDATE temperature
SET value = 24.1
WHERE device_id = 'device01';
""")

# Delete

cur.execute("""
DELETE FROM temperature
WHERE device_id = 'device01';
""")

conn.commit()
cur.close()
conn.close()