- copy iso to proxmox
    - if you can get to pve local in the browser you can see a spot to upload the iso
        - in the left pannel Datacenter -> hostname ->local and then there should be an iso images button
    - scp /home/chowder/Downloads/ubuntu-22.04.5-live-server-amd64.iso root@192.168.20.137:/var/lib/vz/template/iso

make a vm with 
- 2+ cpus
- 8 gigs of ram
- ubuntu server
- 32 gigs hard drive

(i had to systemctl restart dbus to get the vm start to work)

on the ubuntu server
- prep
    - get public key copied during install by adding github key
    - add storage drive
        - in proxmox go to hardware → add and add a hard disk

#now get that disk all set up check that the data drive is sdb
lsblk
sudo mkdir -p /mnt/data

sudo parted /dev/sdb -- mklabel gpt
sudo parted /dev/sdb -- mkpart primary ext4 0% 100%
sudo mkfs.ext4 /dev/sdb1
sudo mount /dev/sdb1 /mnt/data

sudo blkid /dev/sdb1
sudo nano /etc/fstab
add this line but with the partition uuid

UUID=232c8649-1e68-4b11-b9ed-f941fbb8d440 /mnt/data ext4 defaults 0 2

sudo mount -a

    - install minio
sudo apt update && sudo apt install -y curl wget unzip
wget https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x minio
sudo mv minio /usr/local/bin/

sudo useradd -r minio-user -s /sbin/nologin

sudo chown minio-user:minio-user /mnt/data

sudo mkdir -p /etc/minio


###### this is where you change the admin password#####
sudo tee /etc/minio/minio.conf >/dev/null <<'EOF'
MINIO_VOLUMES="/mnt/data"
MINIO_OPTS="--console-address :9001"
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=mySuperSecret
EOF
sudo chmod 600 /etc/minio/minio.conf

#create a systemd unit
sudo tee /etc/systemd/system/minio.service >/dev/null <<'EOF'
[Unit]
Description=MinIO Object Storage
Wants=network-online.target
After=network-online.target

[Service]
User=minio-user
Group=minio-user
EnvironmentFile=/etc/minio/minio.conf
ExecStart=/usr/local/bin/minio server $MINIO_OPTS $MINIO_VOLUMES
Restart=always
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

#enable at start
sudo systemctl daemon-reload
sudo systemctl enable --now minio
sudo systemctl status minio --no-pager
journalctl -u minio -n 50 --no-pager


    
    the web ui is at http://192.168.10.202:9001/login



on dev machine to sync a file to a bucket

wget https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x mc
sudo mv mc /usr/local/bin/

mc alias set minio-vm http://192.168.20.139:9000 minioadmin minioadminpassword

mc mb minio-vm/my-bucket

mc mirror Documents/workingData/ minio-vm/workingdata