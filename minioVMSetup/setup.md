make a vm with 
- 2+ cpus
- 8 gigs of ram
- ubuntu server
- 32 gigs hard drive


on vm
- prep
    - get public key copied (figure out a more secure way to do this)
        - on VM
            - nc your-local-ip 9000 >> ~/.ssh/authorized_keys
        - on remote
            - cat ~/.ssh/id_ed25519.pub | nc -l -p 9000
    - add storage drive
        - in proxmox go to hardware → add and add a hard disk
        
        sudo mkdir -p /mnt/data
        
        sudo parted /dev/sdb -- mklabel gpt
        sudo parted /dev/sdb -- mkpart primary ext4 0% 100%
        sudo mkfs.ext4 /dev/sdb1
        sudo mount /dev/sdb1 /mnt/data
        
        sudo blkid /dev/sdb1
        sudo nano /etc/fstab
        add this line but with the partition uuid
        
        UUID=3ee35b9a-e74a-4280-80ad-7c4624183c97 /mnt/data ext4 defaults 0 2
        
        sudo mount -a
    - install minio
        sudo apt update && sudo apt install -y curl wget unzip
        wget https://dl.min.io/server/minio/release/linux-amd64/minio
        chmod +x minio
        sudo mv minio /usr/local/bin/

        sudo useradd -r minio-user -s /sbin/nologin

        sudo chown minio-user:minio-user /mnt/data

        export MINIO_ROOT_USER=minioadmin
        export MINIO_ROOT_PASSWORD=mySuperSecret



on dev machine to sync a file to a bucket

wget https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x mc
sudo mv mc /usr/local/bin/

mc alias set minio-vm http://192.168.20.139:9000 minioadmin minioadminpassword

mc mb minio-vm/my-bucket

mc mirror Documents/workingData/ minio-vm/workingdata