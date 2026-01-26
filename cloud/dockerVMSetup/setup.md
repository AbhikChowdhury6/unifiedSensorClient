- copy iso to proxmox
    - if you can get to pve local in the browser you can see a spot to upload the iso
        - in the left pannel Datacenter -> hostname ->local and then there should be an iso images button
    - scp /home/chowder/Downloads/ubuntu-22.04.5-live-server-amd64.iso root@192.168.20.137:/var/lib/vz/template/iso

make a vm with 
- 2+ cpus (2 for the testing one)
- 8 gigs of ram (2 for the testing one)
- ubuntu server
- 64 gigs hard drive


start the vm and click install ubuntu

install openssh server and use my github identity to authenticate


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