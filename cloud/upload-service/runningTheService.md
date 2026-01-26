#make a vm with 128gigs of Disk
#4 CPUs
#8 gigs of ram


git clone https://github.com/AbhikChowdhury6/unifiedSensorClient.git

cd unifiedSensorClient/cloud/upload-service/

# copy the upload service files onto the VM (pick one option)
# Option A: from your local machine (example):
# scp -r VMs/upload-service/ user@VM_IP:/opt/upload-service
# Option B: clone your repo directly on the VM (replace URL):
# git clone https://your.git.repo.git /opt/upload-service

# go to the upload service directory
cd /opt/upload-service

#update the app/exsecrets.env file with the minio secrets
#rename to secrets.env

# build and start the stack
docker compose build
docker compose up -d

# check containers
docker compose ps

# follow FastAPI logs
docker compose logs -f fastapi



# test the upload endpoint (replace FILE and VM_IP):
# file name should end with a timestamp like _YYYYMMDDTHHMMSSp123Z.ext
curl -f -X POST \
  -F "file=@/path/to/sample_20250101T000000p123Z.mp4" \
  http://VM_IP/upload

# stop the stack
docker compose down

# stop and remove everything including volumes (CAUTION: deletes MinIO/DB data)
docker compose down -v
