download the latest debian netist
install with full disk encryption

#network setup
set -euo pipefail

### === EDIT THESE ===
IFACE="enp7s0"
IP4="192.168.20.34"
CIDR="24"
GATEWAY="192.168.20.1"
DNS1="192.168.20.1"
DNS2="1.1.1.1"
SEARCH_DOMAIN="proxmoxdeb.local"
HOSTNAME="chowderTest"
BRIDGE="vmbr0"
### ===================

IP_CIDR="${IP4}/${CIDR}"
FQDN="${HOSTNAME}.${SEARCH_DOMAIN}"

echo "[1/7] Sanity check"
ip link show "$IFACE" >/dev/null

echo "[2/7] Ensure ifupdown networking is used at boot (for /etc/network/interfaces)"
apt update
apt install -y ifupdown2
systemctl enable --now networking.service
systemctl disable --now NetworkManager 2>/dev/null || true

echo "[3/7] Write persistent /etc/network/interfaces"
cp -a /etc/network/interfaces "/etc/network/interfaces.bak.$(date +%F-%H%M%S)" 2>/dev/null || true
cat >/etc/network/interfaces <<EOF
auto lo
iface lo inet loopback

allow-hotplug $IFACE
iface $IFACE inet manual

auto $BRIDGE
iface $BRIDGE inet static
  address $IP_CIDR
  gateway $GATEWAY
  bridge-ports $IFACE
  bridge-stp off
  bridge-fd 0
  dns-nameservers $DNS1 $DNS2
  dns-search $SEARCH_DOMAIN
EOF

echo "[4/7] Ensure hostname resolves to the management IP (required for pve-cluster)"
echo "$HOSTNAME" >/etc/hostname

# Rewrite /etc/hosts safely (keep localhost; ensure non-loopback mapping exists)
cp -a /etc/hosts "/etc/hosts.bak.$(date +%F-%H%M%S)" 2>/dev/null || true
grep -vE "^\s*${IP4//./\\.}\s+|^\s*127\.\S+\s+${HOSTNAME}(\s|$)" /etc/hosts > /etc/hosts.new || true
# ensure localhost line exists
grep -qE '^\s*127\.0\.0\.1\s+localhost' /etc/hosts.new || echo "127.0.0.1 localhost" >> /etc/hosts.new
echo "$IP4 $FQDN $HOSTNAME" >> /etc/hosts.new
mv /etc/hosts.new /etc/hosts

echo "[5/7] Apply networking (restart service) + fallback if needed"
systemctl restart networking.service || true

# If vmbr0 still missing, do manual bridge bring-up (keeps you from getting stuck)
if ! ip link show "$BRIDGE" >/dev/null 2>&1; then
  ip link add "$BRIDGE" type bridge 2>/dev/null || true
  ip link set "$IFACE" up
  ip link set "$IFACE" master "$BRIDGE"
  ip addr flush dev "$IFACE" || true
  ip addr add "$IP_CIDR" dev "$BRIDGE" || true
  ip link set "$BRIDGE" up
  ip route replace default via "$GATEWAY"
fi

echo "[6/7] Lid-close: prevent suspend"
cp -a /etc/systemd/logind.conf "/etc/systemd/logind.conf.bak.$(date +%F-%H%M%S)" 2>/dev/null || true
# Make sure settings exist and are set to ignore
sed -i 's/^[# ]*HandleLidSwitch=.*/HandleLidSwitch=ignore/' /etc/systemd/logind.conf || true
sed -i 's/^[# ]*HandleLidSwitchExternalPower=.*/HandleLidSwitchExternalPower=ignore/' /etc/systemd/logind.conf || true
sed -i 's/^[# ]*HandleLidSwitchDocked=.*/HandleLidSwitchDocked=ignore/' /etc/systemd/logind.conf || true

# If keys didn't exist, append them under [Login]
grep -q '^\[Login\]' /etc/systemd/logind.conf || printf '\n[Login]\n' >> /etc/systemd/logind.conf
grep -q '^HandleLidSwitch=' /etc/systemd/logind.conf || echo 'HandleLidSwitch=ignore' >> /etc/systemd/logind.conf
grep -q '^HandleLidSwitchExternalPower=' /etc/systemd/logind.conf || echo 'HandleLidSwitchExternalPower=ignore' >> /etc/systemd/logind.conf
grep -q '^HandleLidSwitchDocked=' /etc/systemd/logind.conf || echo 'HandleLidSwitchDocked=ignore' >> /etc/systemd/logind.conf

systemctl restart systemd-logind

echo "[7/7] Verify"
ip -br addr show "$BRIDGE" || true
getent hosts "$HOSTNAME" || true
ping -c 2 "$GATEWAY" || true





#install proxmox trixie
apt update
apt install -y wget ca-certificates gnupg

wget https://enterprise.proxmox.com/debian/proxmox-archive-keyring-trixie.gpg \
  -O /usr/share/keyrings/proxmox-archive-keyring.gpg
chmod 0644 /usr/share/keyrings/proxmox-archive-keyring.gpg

cat > /etc/apt/sources.list.d/pve-no-subscription.sources <<'EOF'
Types: deb
URIs: http://download.proxmox.com/debian/pve
Suites: trixie
Components: pve-no-subscription
Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg
EOF

for f in /etc/apt/sources.list.d/*enterprise* /etc/apt/sources.list.d/pve-enterprise.*; do
  [ -e "$f" ] && mv "$f" "$f.disabled"
done

apt update
apt full-upgrade -y

# install kernel first, then reboot (optional but clean)
apt install -y proxmox-default-kernel
reboot



apt update
apt install -y proxmox-ve postfix open-iscsi chrony

# quick health checks
pveversion -v || true
systemctl --no-pager --full status pve-cluster pveproxy pvedaemon || true
ss -lntp | grep ':8006' || true


# access at https://192.168.20.34:8006 use root with root password



