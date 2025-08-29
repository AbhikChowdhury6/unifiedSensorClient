# this file will evolve based on features
testpi5UUID = "c57d828b-e8d1-433b-ad79-5420d2136d3f"


platform_uuid = testpi5UUID

# this is the platform name
platform_name = "raspberry_pi_5"

# this is the responsible party
responsible_party = "Abhik"

csv_writer_subscriptions = [
    f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature.sock",
    f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity.sock",
    f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure.sock",
]

# the write locations, note the file name will be the topic name.csv
csv_writer_write_location = [
    "/home/pi/csv_writer/data",
]

i2c_controller_config = {
    "bus_number": 0,
    "devices": [
        {   
            "class": "bme280",
            "manufacturer": "bosch",
            "model": "bme280",
            "address": 77,
            "sensors": [
                {
                    "name": "air-temprature",
                    "topic": f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature.sock",
                },
                {
                    "name": "relative-humidity",
                    "topic": f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity.sock",
                },
                {
                    "name": "barometric-pressure",
                    "topic": f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure.sock",
                },
            ],
        }
    ]
}
