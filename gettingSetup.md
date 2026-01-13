conda install -y zeromq pyzmq msgpack-python python-sounddevice setproctitle colorlog

pip3 install adafruit-extended-bus
pip3 install adafruit-circuitpython-scd4x
pip3 install adafruit-circuitpython-pm25
pip3 install adafruit-circuitpython-bme280
pip3 install adafruit-circuitpython-bme680
pip3 install adafruit-circuitpython-bno08x
pip3 install adafruit-circuitpython-gps
pip3 install lgpio qoi
//sudo pip3 install rpi_ws281x adafruit-circuitpython-neopixel

sudo pip3 install adafruit-circuitpython-neopixel-spi


#how to do memory compression


#nmcli connection show
#nmcli con down snet5
#nmcli device wifi connect snet24 password secret
#nmcli con delete snet 5


sudo apt install wavpack
which wavpack && wavpack --version
which wvunpack && wvunpack --version



add this to /boot/firmware/config.txt
dtparam=i2c_arm_baudrate=400000


#libcamera-vid --width 1920 --height 1080 -t 0 --inline --listen -o tcp://0.0.0.0:8888
#mpv --fps=40 --demuxer-lavf-probesize=32 tcp://192.168.10.67:8888/




wifi reliability

# Global NM tweaks
sudo tee /etc/NetworkManager/conf.d/wifi-solid.conf >/dev/null <<'EOF'
[connection]
wifi.powersave=2           # 2 = disable powersave

[device]
wifi.scan-rand-mac-address=no
EOF

sudo systemctl restart NetworkManager


sudo nmcli con mod "dnet24" connection.autoconnect yes
sudo nmcli con mod "dnet24" connection.autoconnect-retries -1     # keep retrying forever
sudo nmcli con mod "dnet24" 802-11-wireless.cloned-mac-address permanent
sudo nmcli con mod "dnet24" ipv6.method ignore                     # optional: avoid IPv6 DHCP bugs
sudo nmcli con up  "dnet24"


# Once per boot via systemd (preferred over cron)
sudo tee /etc/systemd/system/wifi-nosleep.service >/dev/null <<'EOF'
[Unit]
Description=Disable WiFi power save
After=network.target

[Service]
Type=oneshot
ExecStart=/sbin/iw dev wlan0 set power_save off
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now wifi-nosleep.service


sudo nano /usr/local/sbin/wifi-heal.sh



