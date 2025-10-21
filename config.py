import multiprocessing as mp

# this file will evolve based on features
testpi5UUID = "c57d828b-e8d1-433b-ad79-5420d2136d3f"


platform_uuid = testpi5UUID

zmq_control_endpoint = f"ipc:///tmp/{platform_uuid}_control.sock"
# separate inbound requests endpoint (workers PUB -> main SUB)
zmq_control_requests_endpoint = f"ipc:///tmp/{platform_uuid}_control_requests.sock"

# this is the platform name
platform_name = "raspberry_pi_5"

# this is the responsible party
responsible_party = "Abhik"

#a reminder about levels and numbers
#- trace (not built in) (5)
#- debug (10)
#- info (20)
#- warning (30)
#- error (40)
#- critical (50)
main_debug_lvl = 20

logging_process_config = {
    "module_name": "logUtils",
    "func_name": "logging_process",
    "short_name": "logging",
    "time_to_shutdown": .1,
    "debug_lvl": 20,
    "logfile_path": "/home/pi/unifiedSensorClient.log",
}


file_uploader_process_config = {
    "module_name": "fileUploader",
    "func_name": "file_uploader",
    "short_name": "file-up",
    "time_to_shutdown": .1,
    "debug_lvl": 20,
    "upload_url": "http://192.168.10.36:/upload",
    "upload_retry_interval": 10,
    "subscription_endpoints": [
        f"ipc:///tmp/{platform_uuid}_mp4_writer.sock",
        f"ipc:///tmp/{platform_uuid}_audio_writer.sock",
    ],
    "subscription_topics": [
        f"{platform_uuid}_mp4_writer",
        f"{platform_uuid}_audio_writer",
    ],
    "time_till_ready": 20, # this has to be longer than the delete process time before
    "data_dir": "/home/pi/data/",


}

csv_writer_process_config = {
    "func_name": "csv_writer",
    "module_name": "csvWriter",
    "short_name": "csv",
    "time_to_shutdown": .1,
    "write_location": "/home/pi/data/csv_writer/",
    "subscription_endpoints": [
        f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius.sock",
        f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent.sock",
        f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa.sock",
    ],
    "subscription_topics": [
        f"{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius",
        f"{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent",
        f"{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa",
    ],
}

sqlite_writer_write_location = "/home/pi/sqlite_writer/"

sqlite_writer_process_config = {
    "module_name": "sqliteWriter",
    "func_name": "sqlite_writer",
    "short_name": "sqlite",
    "time_to_shutdown": .1,
    "debug_lvl": 20,
    "write_location": sqlite_writer_write_location,
    "subscription_endpoints": [
        f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius.sock",
        f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent.sock",
        f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa.sock",
        f"ipc:///tmp/{platform_uuid}_yolo11m_person_detection.sock",
#        f"ipc:///tmp/{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gps3dFix.sock",
#        f"ipc:///tmp/{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gpsSpeed.sock",
#        f"ipc:///tmp/{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gpsEPEP.sock",
    ],
    "subscription_topics": [
        f"{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius",
        f"{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent",
        f"{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa",
        f"{platform_uuid}_yolo11m_person_detection",
#        f"{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gps3dFix",
#        f"{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gpsSpeed",
#        f"{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gpsEPEP",
    ],
}

# note all sensors are floats and are in units standard for the sensor

i2c_controller_process_config = {
    "module_name": "i2cController",
    "func_name": "i2c_controller",
    "short_name": "i2c",
    "time_to_shutdown": .1,
    "bus_number": 1,
    "debug_lvl": 20,
    "devices": [
        {   
            "module_name": "abme280",
            "class_name": "aBME280",
            "manufacturer": "bosch",
            "model": "bme280",
            "address": 0x76,
            "debug_lvl": 20,
            "sensors": [
                {
                    "sensor_type": "barometric-pressure-pa",
                    "topic": f"{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa",
                    "endpoint": f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa.sock",
                    "update_hz": 16,
                    "rounding_bits": 0,
                    "short_name": "i2c",
                    "debug_lvl": 20,
                },
                {
                    "sensor_type": "air-temprature-celcius",
                    "topic": f"{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius",
                    "endpoint": f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius.sock",
                    "update_hz": 1,
                    "rounding_bits": 5,
                    "short_name": "i2c",
                    "debug_lvl": 20,
                },
                {
                    "sensor_type": "relative-humidity-percent",
                    "topic": f"{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent",
                    "endpoint": f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent.sock",
                    "update_hz": .25,
                    "rounding_bits": 4,
                    "short_name": "i2c",
                    "debug_lvl": 20,
                },
            ],
        }
    ]
}


picamv3noirwide = "picamV3-sony-imx708-noir-120fov-12MP"
picamv3noir = "picamV3-sony-imx708-noir-80fov-12MP"
picamv3wide = "picamV3-sony-imx708-120fov-12MP"

video_controller_process_config = {
    "module_name": "videoController",
    "func_name": "video_controller",
    "short_name": "video",
    "time_to_shutdown": .25,
    "debug_lvl": 20,
    "camera_type_module": "piCamera",
    "camera_type_class": "PiCamera",
    "camera_index": 0,
    "camera_type": picamv3noirwide,
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "camera_width": 1920,
    "camera_height": 1080,
    "format": "RGB888",
    "fps": 8,
    "subsample_ratio": 2,
    "timestamp_images": True,
}


mp4_writer_process_config = {
    "module_name": "mp4Writer",
    "func_name": "mp4_writer",
    "short_name": "mp4",
    "time_to_shutdown": .1,
    "debug_lvl": 20,
    "write_location": "/home/pi/data/mp4_writer/",
    "file_base": f"{platform_uuid}_csi-0_{picamv3noirwide}_mp4",
    "subscription_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "subscription_topic": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "publish_topic": f"{platform_uuid}_mp4_writer",
    "publish_endpoint": f"ipc:///tmp/{platform_uuid}_mp4_writer.sock",
    "duration_s": 4,
    "container_type": "mp4",
    "loglevel": "warning",
    "codec": "h264",
    "quality": 80,
    "keyframe_interval_seconds": 2,
    "fps": 8,
    "frame_gap_restart_seconds": .5,
    "format": "RGB888",
}


jpeg_writer_process_config = {
    "module_name": "jpegWriter",
    "func_name": "jpeg_writer",
    "short_name": "jpeg",
    "time_to_shutdown": .1,
    "file_base": f"{platform_uuid}_csi-0_{picamv3noirwide}_jpeg",
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "debug_lvl": 20,
    "write_location": "/home/pi/data/jpeg_writer/",
    "capture_tolerance_seconds": 0.25,
    "quality": 90,
    "image_interval_seconds": 16,
}

yolo_person_detector_process_config = {
    "module_name": "yoloPersonDetector",
    "func_name": "yolo_person_detector",
    "short_name": "yolo",
    "time_to_shutdown": 3,
    "debug_lvl": 10,
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "pub_endpoint": f"ipc:///tmp/{platform_uuid}_yolo11m_person_detection.sock",
    "pub_topic": f"{platform_uuid}_yolo11m_person_detection",
    "model": "yolo11s",
    "confidence_threshold": 0.5,
    "nms_threshold": 0.5,
    "interval_seconds": 4,
    "verbose": True,
}

audio_controller_process_config = {
    "module_name": "audioController",
    "func_name": "audio_controller",
    "short_name": "audio",
    "time_to_shutdown": .6,
    "debug_lvl": 20,
    "pub_endpoint": f"ipc:///tmp/{platform_uuid}_audio_controller.sock",
    "pub_topic": f"{platform_uuid}_audio_controller",
    "sample_rate": 16000,
    "channels": 1,
    "hz": 2,
    "dtype": "int16",
}

audio_writer_process_config = {
    "module_name": "audioWriter",
    "func_name": "audio_writer",
    "short_name": "opus",
    "time_to_shutdown": .1,
    "debug_lvl": 20,
    "sub_endpoint": f"ipc:///tmp/{platform_uuid}_audio_controller.sock",
    "sub_topic": f"{platform_uuid}_audio_controller",
    "write_location": "/home/pi/data/audio_writer/",
    "bitrate": "16k",
    "sample_rate": 16000,
    "channels": 1,
    "application": "audio",
    "frame_duration_ms": 40,
    "duration_s": 4,
    "loglevel": "warning",
#    "device": "plughw:CARD=MICTEST,DEV=0",
#    "device": "plughw:CARD=Device,DEV=0",
    "frame_hz": 2,
}

detector_based_deleter_process_config = {
    "module_name": "detectorBasedDeleter",
    "func_name": "detector_based_deleter",
    "short_name": "del",
    "time_to_shutdown": .1,
    "debug_lvl": 20,
    "detector_names": [f"{platform_uuid}_yolo11m_person_detection"],
    "detector_endpoints": [f"ipc:///tmp/{platform_uuid}_yolo11m_person_detection.sock"],
    "files_location": "/home/pi/data/mp4_writer/",
    "mp4_writer_topic": f"{platform_uuid}_mp4_writer",
    "mp4_writer_endpoint": f"ipc:///tmp/{platform_uuid}_mp4_writer.sock",
    "seconds_after_keep": 20,
    "seconds_before_keep": 10,
}

is_dark_detector_process_config = {
    "module_name": "isDarkDetector",
    "func_name": "is_dark_detector",
    "short_name": "dark",
    "time_to_shutdown": .1,
    "debug_lvl": 20,
    "pub_topic": f"{platform_uuid}_is_dark_detector",
    "pub_endpoint": f"ipc:///tmp/{platform_uuid}_is_dark_detector.sock",
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "threshold": 0.5,
    "interval_seconds": 1,
}

motion_detector_process_config = {
    "module_name": "motionDetector",
    "func_name": "motion_detector",
    "short_name": "motion",
    "time_to_shutdown": .1,
    "debug_lvl": 10,
    "pub_topic": f"{platform_uuid}_motion_detector",
    "pub_endpoint": f"ipc:///tmp/{platform_uuid}_motion_detector.sock",
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "threshold": 50,
    "interval_seconds": 1,
}

pigpio_toggle_buttons_process_config = {
    "module_name": "pigpioButtons",
    "func_name": "pigpio_buttons",
    "short_name": "buttons",
    "time_to_shutdown": .1,
    "debug_lvl": 20,
    "button_sense_pins": [[20, "low"], [12, "low"], [7, "high"]],
    "set_high_pins": [21, 16],
    "set_low_pins": [],
    "button_message_map": {
        17: [[['d', 'video']], [['e', 'video']]],
        27: [[['d', 'audio']], [['e', 'audio']]],
        26: [
            [['e', 'yolo'], ['e', 'del'], ['d', "motion"], ['d', "dark"]], # yolo only
            [['d', 'yolo'], ['e', 'del'], ['e', 'motion'], ['d', 'dark']], # motion only
            [['d', 'yolo'], ['e', 'del'], ['d', 'motion'], ['e', 'dark']], # dark only
            [['d', 'yolo'], ['d', 'del'], ['d', 'motion'], ['d', 'dark']], # off
        ],
    },
    "button_endpoint": f"ipc:///tmp/control.sock",
}

connection_check_process_config = {
    "module_name": "connectionCheck",
    "func_name": "connection_check",
    "short_name": "check",
    "time_to_shutdown": .1,
    "debug_lvl": 20,
    "pub_topic": f"{platform_uuid}_connection_check",
    "pub_endpoint": f"ipc:///tmp/{platform_uuid}_connection_check.sock",
    "interval_seconds": 1,
    "states": ["offline", "hotspot", "home-wifi"],
    "ssids": {"hotspot": "chowderphone", "home-wifi": "snet24"},
}

led_controller_process_config = {
    "module_name": "ledController",
    "func_name": "led_controller",
    "short_name": "led",
    "time_to_shutdown": .1,
    "debug_lvl": 20,
    "pub_topic": "control",
    # for requests to main, publish to the dedicated requests endpoint
    "pub_endpoint": zmq_control_requests_endpoint,
    "states": {0 : {(255, 0, 0): set([(1, 'video')]), (0, 0, 0): set([(0, 'video')])},
               1 : {(0, 255, 0): set([(1, 'audio')]), (0, 0, 0): set([(0, 'audio')])},
               2 : {(255, 0, 0): set([(1, 'yolo'), (1, 'del'), (0, "motion"), (0, "dark")]), # yolo only
                    (0, 255, 0): set([(0, 'yolo'), (1, 'del'), (1, 'motion'), (0, 'dark')]), # motion only
                    (0, 0, 255): set([(0, 'yolo'), (1, 'del'), (0, 'motion'), (1, 'dark')]), # dark only
                    (0, 0, 0): set([(0, 'yolo'), (0, 'del'), (0, 'motion'), (0, 'dark')]), # off
                },
    },
}

gps_capture_process_config = {
    "module_name": "gpsCapture",
    "func_name": "gps_capture",
    "short_name": "gps",
    "time_to_shutdown": 1,
    "debug_lvl": 20,
    "baudrate": 9600,
    "timeout": 10,
    "update_hz": 1,
    "serial_port": "ttyUSB0",
    "pub_topic_3dFix": f"{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gps3dFix",
    "pub_endpoint_3dFix": f"ipc:///tmp/{platform_uuid}_serial_ttyUSB0_adafruit_PA1616S_gps3dFix.sock",
    "pub_topic_speed": f"{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gpsSpeed",
    "pub_endpoint_speed": f"ipc:///tmp/{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gpsSpeed.sock",
    "pub_topic_epe": f"{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gpsEPEP",
    "pub_endpoint_epe": f"ipc:///tmp/{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gpsEPEP.sock",
}


all_process_configs = {
    "csv": [0, csv_writer_process_config],
    "sqlite": [1, sqlite_writer_process_config],
    "i2c": [1, i2c_controller_process_config],
    "video": [1, video_controller_process_config],
    "mp4": [1, mp4_writer_process_config],
    "jpeg": [1, jpeg_writer_process_config],
    "yolo": [1, yolo_person_detector_process_config],
    "audio": [1, audio_controller_process_config],
    "opus": [1, audio_writer_process_config],
    "dark": [0, is_dark_detector_process_config],
    "motion": [0, motion_detector_process_config],
    "del": [1, detector_based_deleter_process_config],
#    "buttons": pigpio_toggle_buttons_process_config,
    "led": [0, led_controller_process_config],
    "file-up": [1, file_uploader_process_config],
}