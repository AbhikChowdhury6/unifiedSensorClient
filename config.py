# this file will evolve based on features
testpi5UUID = "c57d828b-e8d1-433b-ad79-5420d2136d3f"


platform_uuid = testpi5UUID

zmq_control_endpoint = f"ipc:///tmp/{platform_uuid}_control.sock"

# this is the platform name
platform_name = "raspberry_pi_5"

# this is the responsible party
responsible_party = "Abhik"

csv_writer_subscription_endpoints = [
    f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature.sock",
    f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity.sock",
    f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure.sock",
]

csv_writer_subscription_topics = [
    f"{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature",
    f"{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity",
    f"{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure",
]
# the write locations, note the file name will be the topic name.csv
csv_writer_write_location = [
    "/home/pi/csv_writer/data/",
]


# note all sensors are floats and are in units standard for the sensor

i2c_controller_config = {
    "bus_number": 0,
    "devices": [
        {   
            "module_name": "abme280",
            "class_name": "aBME280",
            "manufacturer": "bosch",
            "model": "bme280",
            "address": 0x77,
            "sensors": [
                {
                    "sensor_type": "air-temprature",
                    "topic": f"{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature.sock",
                    "endpoint": f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature.sock",
                    "update_hz": 1,
                    "rounding_bits": 5,
                },
                {
                    "sensor_type": "relative-humidity",
                    "topic": f"{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity.sock",
                    "endpoint": f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity.sock",
                    "update_hz": .25,
                    "rounding_bits": 4,
                },
                {
                    "sensor_type": "barometric-pressure",
                    "topic": f"{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure.sock",
                    "endpoint": f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure.sock",
                    "update_hz": 16,
                    "rounding_bits": 0,
                },
            ],
        }
    ]
}
