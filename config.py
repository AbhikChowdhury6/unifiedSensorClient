import multiprocessing as mp

# this file will evolve based on features
testpi5UUID = "c57d828b-e8d1-433b-ad79-5420d2136d3f"


platform_uuid = testpi5UUID

zmq_control_endpoint = f"ipc:///tmp/{platform_uuid}_control.sock"

# this is the platform name
platform_name = "raspberry_pi_5"

# this is the responsible party
responsible_party = "Abhik"

log_queue = None

def init_log_queue():
    global log_queue
    if log_queue is None:
        log_queue = mp.Queue()
    return log_queue

def get_log_queue():
    global log_queue
    if log_queue is None:
        raise RuntimeError("Log queue not initialized. Call init_log_queue() first.")
    return log_queue

allowed_loggers = []
allowed_funcs = []
debugLvl = 10


csv_writer_process_config = {
    "module_name": "csvWriter",
    "class_name": "csv_writer",
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

sqlite_writer_process_config = {
    "module_name": "sqliteWriter",
    "class_name": "sqlite_writer",
    "short_name": "sqlite",
    "time_to_shutdown": .1,
    "write_location": "/home/pi/data/sqlite_writer/",
    "subscription_endpoints": [
        f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius.sock",
        f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent.sock",
        f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa.sock",
        f"ipc:///tmp/{platform_uuid}_yolo11m_person_detection.sock",
    ],
    "subscription_topics": [
        f"{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius",
        f"{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent",
        f"{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa",
        f"{platform_uuid}_yolo11m_person_detection",
    ],
}

# note all sensors are floats and are in units standard for the sensor

i2c_controller_process_config = {
    "module_name": "i2cController",
    "class_name": "i2c_controller",
    "short_name": "i2c",
    "time_to_shutdown": .1,
    "bus_number": 1,
    "devices": [
        {   
            "module_name": "abme280",
            "class_name": "aBME280",
            "manufacturer": "bosch",
            "model": "bme280",
            "address": 0x76,
            "sensors": [
                {
                    "sensor_type": "barometric-pressure-pa",
                    "topic": f"{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa",
                    "endpoint": f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa.sock",
                    "update_hz": 16,
                    "rounding_bits": 0,
                },
                {
                    "sensor_type": "air-temprature-celcius",
                    "topic": f"{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius",
                    "endpoint": f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius.sock",
                    "update_hz": 1,
                    "rounding_bits": 5,
                },
                {
                    "sensor_type": "relative-humidity-percent",
                    "topic": f"{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent",
                    "endpoint": f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent.sock",
                    "update_hz": .25,
                    "rounding_bits": 4,
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
    "class_name": "video_controller",
    "short_name": "video",
    "time_to_shutdown": .25,
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
    "class_name": "mp4_writer",
    "short_name": "mp4",
    "time_to_shutdown": .1,
    "write_location": "/home/pi/data/mp4_writer/",
    "subscription_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "subscription_topic": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "publish_topic": f"{platform_uuid}_mp4_writer",
    "publish_endpoint": f"ipc:///tmp/{platform_uuid}_mp4_writer.sock",
    "video_duration": 4,
    "container_type": "mp4",
    "codec": "h264",
    "quality": 80,
    "keyframe_interval_seconds": 2,
    "fps": 8,
    "frame_gap_restart_seconds": .5,
    "format": "RGB888",
}


jpeg_writer_process_config = {
    "module_name": "jpegWriter",
    "class_name": "jpeg_writer",
    "short_name": "jpeg",
    "time_to_shutdown": .1,
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "write_location": "/home/pi/data/jpeg_writer/",
    "capture_tolerance_seconds": 0.25,
    "quality": 90,
    "image_interval_seconds": 16,
}

yolo_person_detector_process_config = {
    "module_name": "yoloPersonDetector",
    "class_name": "yolo_person_detector",
    "short_name": "yolo",
    "time_to_shutdown": 3,
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "pub_endpoint": f"ipc:///tmp/{platform_uuid}_yolo11m_person_detection.sock",
    "pub_topic": f"{platform_uuid}_yolo11m_person_detection",
    "model": "yolo11m",
    "confidence_threshold": 0.7,
    "nms_threshold": 0.7,
    "interval_seconds": 4,
    "verbose": False,
}

audio_controller_process_config = {
    "module_name": "audioController",
    "class_name": "audio_controller",
    "short_name": "audio",
    "time_to_shutdown": .6,
    "pub_endpoint": f"ipc:///tmp/{platform_uuid}_audio_controller.sock",
    "pub_topic": f"{platform_uuid}_audio_controller",
    "sample_rate": 16000,
    "channels": 1,
    "hz": 2,
    "dtype": "int16",
}

audio_writer_process_config = {
    "module_name": "audioWriter",
    "class_name": "audio_writer",
    "short_name": "opus",
    "time_to_shutdown": .1,
    "sub_endpoint": f"ipc:///tmp/{platform_uuid}_audio_controller.sock",
    "sub_topic": f"{platform_uuid}_audio_controller",
    "write_location": "/home/pi/data/audio_writer/",
    "bitrate": "16k",
    "sample_rate": 16000,
    "channels": 1,
    "application": "audio",
    "frame_duration_ms": 40,
    "segment_time_s": 4,
    "loglevel": "warning",
    "alsa_device": "plughw:CARD=MICTEST,DEV=0",
    "frame_hz": 2,
}

detector_based_deleter_process_config = {
    "module_name": "detectorBasedDeleter",
    "class_name": "detector_based_deleter",
    "short_name": "del",
    "time_to_shutdown": .1,
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
    "class_name": "is_dark_detector",
    "short_name": "dark",
    "time_to_shutdown": .1,
    "pub_topic": f"{platform_uuid}_is_dark_detector",
    "pub_endpoint": f"ipc:///tmp/{platform_uuid}_is_dark_detector.sock",
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "threshold": 0.5,
    "interval_seconds": 1,
}

motion_detector_process_config = {
    "module_name": "motionDetector",
    "class_name": "motion_detector",
    "short_name": "motion",
    "time_to_shutdown": .1,
    "pub_topic": f"{platform_uuid}_motion_detector",
    "pub_endpoint": f"ipc:///tmp/{platform_uuid}_motion_detector.sock",
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "threshold": 50,
    "interval_seconds": 1,
}

pigpio_toggle_buttons_process_config = {
    "module_name": "pigpioButtons",
    "class_name": "pigpio_buttons",
    "short_name": "buttons",
    "time_to_shutdown": .1,
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


all_process_configs = {
    "csv": csv_writer_process_config,
    "sqlite": sqlite_writer_process_config,
    "i2c": i2c_controller_process_config,
    "video": video_controller_process_config,
    "mp4": mp4_writer_process_config,
    "jpeg": jpeg_writer_process_config,
    "yolo": yolo_person_detector_process_config,
    "audio": audio_controller_process_config,
    "opus": audio_writer_process_config,
    "del": detector_based_deleter_process_config,
}