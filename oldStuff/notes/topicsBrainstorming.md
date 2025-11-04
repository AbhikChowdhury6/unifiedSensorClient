so we'll have sensor topics
sensor
- bme280_temprature_C_datainstanceID

separate table with 
- instanceID to owner, device name
- if I recall we were going to organize it by
  the only immutable thing was the platform UUID
- each sensor device also has an instance ID?


- i.e. two IMU's, two cameras at the same time
  upgrading a camera to a new sensor, upgrading to a 680
  how about we just use unique sensor names
  like picamV3-sony-imx708-12MP as well as unique interface names

- platform UUID, interface name, device name, sensor name
  if any of these change it's a different sensor

- on the backend platfrom UUID is tied to
  immutable: platform name, responsible party, 3 words
  mutable: instance given name

so back to topics we'll set it up were
plarformUUID_i2c-0_bosch-bme280-77_air-temprature
plarformUUID_i2c-0_bosch-bme280-77_relative-humidity
plarformUUID_i2c-0_bosch-bme280-77_barometric-pressure

testpi5UUID = c57d828b-e8d1-433b-ad79-5420d2136d3f 



alright I feel like we have a good way of getting the
csv writer to know about all of the sockets to subscribe to

now how do we want to get the sensors spun up, I feel like
the last way we were soing it was a bit over complicated

i2c controller gets spun up with it config
 - bus number

it imports all of the classes it needs and passes in config

it