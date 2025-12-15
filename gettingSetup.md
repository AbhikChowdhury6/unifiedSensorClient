conda install -y zeromq pyzmq msgpack-python python-sounddevice setproctitle colorlog


pip3 install adafruit-circuitpython-scd4x
pip3 install adafruit-circuitpython-pm25
pip3 install adafruit-circuitpython-bme280
pip3 install adafruit-circuitpython-bme680
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