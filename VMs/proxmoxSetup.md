download the latest debian netist
install with full disk encryption


#set up ip stuff
ip -br link

##temp network setup
ip addr flush dev enp1s0
ip addr add 192.168.10.34/24 dev enp1s0
ip link set enp1s0 up
ip route replace default via 192.168.10.1
printf 'nameserver 192.168.10.1\nnameserver 1.1.1.1\n' > /etc/resolv.conf


##rest of network setup

ip addr flush dev enp1s0
ip addr add 192.168.10.34/24 dev enp1s0
ip link set enp1s0 up
ip route replace default via 192.168.10.1
printf 'nameserver 192.168.10.1\nnameserver 1.1.1.1\n' > /etc/resolv.conf

apt update
apt install -y ifupdown bridge-utils
# Optional: remove NetworkManager later from local console to avoid brief disconnect
# apt purge -y network-manager || true

cat >/etc/network/interfaces <<'EOF'
auto lo
iface lo inet loopback

# Physical NIC carries no IP; the bridge will hold it.
allow-hotplug enp1s0
iface enp1s0 inet manual

auto vmbr0
iface vmbr0 inet static
  address 192.168.10.34/24
  gateway 192.168.10.1
  bridge-ports enp1s0
  bridge-stp off
  bridge-fd 0
  dns-nameservers 192.168.10.1 1.1.1.1
  dns-search proxmoxdeb.local
EOF


# Try classic init script if present
[ -x /etc/init.d/networking ] && /etc/init.d/networking restart || true

# Or do it directly
ifdown enp1s0 2>/dev/null || true
ifup enp1s0 || true
ifup vmbr0

ip -br addr show vmbr0
ping -c 2 192.168.10.1
ping -c 2 1.1.1.1


#install proxmox trixie
sudo -i
apt install wget
cat > /etc/apt/sources.list.d/pve-install-repo.sources << 'EOF'
Types: deb
URIs: http://download.proxmox.com/debian/pve
Suites: trixie
Components: pve-no-subscription
Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg
EOF
wget https://enterprise.proxmox.com/debian/proxmox-archive-keyring-trixie.gpg -O /usr/share/keyrings/proxmox-archive-keyring.gpg
apt update && apt full-upgrade -y



apt install -y proxmox-default-kernel
reboot

#select local only for postfix
apt install -y proxmox-ve postfix open-iscsi chrony


apt remove -y linux-image-amd64 'linux-image-6.*'
update-grub || true


# access at 192.168.10.34:8006 use root with root password
