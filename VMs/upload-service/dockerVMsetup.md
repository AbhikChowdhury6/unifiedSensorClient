#make a vm with 128gigs of Disk
#4 CPUs
#8 gigs of ram

sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo \
"deb [arch=$(dpkg --print-architecture) \
signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu \
$(lsb_release -cs) stable" | \
sudo tee /etc/apt/sources.list.d/docker.list > /dev/null


sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker $USER

sudo reboot

docker run hello-world





# copy the upload service files onto the VM (pick one option)
# Option A: from your local machine (example):
# scp -r VMs/upload-service/ user@VM_IP:/opt/upload-service
# Option B: clone your repo directly on the VM (replace URL):
# git clone https://your.git.repo.git /opt/upload-service

# go to the upload service directory
cd /opt/upload-service

# build and start the stack (FastAPI + MinIO + TimescaleDB)
docker compose build
docker compose up -d

# check containers
docker compose ps

# follow FastAPI logs
docker compose logs -f fastapi

# (optional) access MinIO console in a browser:
# http://VM_IP:9001  (user: minio, password: minio123)

# test the upload endpoint (replace FILE and VM_IP):
# file name should end with a timestamp like _YYYYMMDDTHHMMSSp123Z.ext
curl -f -X POST \
  -F "file=@/path/to/sample_20250101T000000p123Z.mp4" \
  http://VM_IP/upload

# stop the stack
docker compose down

# stop and remove everything including volumes (CAUTION: deletes MinIO/DB data)
docker compose down -v
