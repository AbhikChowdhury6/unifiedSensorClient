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

csv_writer_subscription_endpoints = [
    f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius.sock",
    f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent.sock",
    f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa.sock",
]

csv_writer_subscription_topics = [
    f"{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius",
    f"{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent",
    f"{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa",
]
# the write locations, note the file name will be the topic name.csv
csv_writer_write_location = "/home/pi/csv_writer/data/"

sqlite_writer_subscription_endpoints = [
    f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius.sock",
    f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent.sock",
    f"ipc:///tmp/{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa.sock",
    f"ipc:///tmp/{platform_uuid}_yolo11m_person_detection.sock",
]

sqlite_writer_write_location = "/home/pi/sqlite_writer/data/"


sqlite_writer_subscription_topics = [
    f"{platform_uuid}_i2c-0_bosch-bme280-77_air-temprature-celcius",
    f"{platform_uuid}_i2c-0_bosch-bme280-77_relative-humidity-percent",
    f"{platform_uuid}_i2c-0_bosch-bme280-77_barometric-pressure-pa",
    f"{platform_uuid}_yolo11m_person_detection",
]

# note all sensors are floats and are in units standard for the sensor

i2c_controller_config = {
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

cameras = [{
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
}]

h264_writer_subscription_endpoints = [
    f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
]

h264_writer_subscription_topics = [
    f"{platform_uuid}_csi-0_{picamv3noirwide}",
]


h264_writer_config = {
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "write_location": "/home/pi/h264_writer/data/",
    "publish_topic": f"{platform_uuid}_h264_writer",
    "publish_endpoint": f"ipc:///tmp/{platform_uuid}_h264_writer.sock",
    "video_duration": 4,
    "container_type": "mp4",
    "codec": "h264",
    "quality": 80,
    "keyframe_interval_seconds": 2,
    "fps": 8,
    "frame_gap_restart_seconds": .5,
    "format": "RGB888",
}

jpeg_writer_config = {
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "write_location": "/home/pi/jpeg_writer/data/",
    "capture_tolerance_seconds": 0.25,
    "quality": 80,
    "image_interval_seconds": 16,
}

yolo_person_detector_config = {
    "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
    "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
    "pub_endpoint": f"ipc:///tmp/{platform_uuid}_yolo11m_person_detection.sock",
    "pub_topic": f"{platform_uuid}_yolo11m_person_detection",
    "model": "yolo11m",
    "confidence_threshold": 0.7,
    "nms_threshold": 0.7,
    "interval_seconds": 4,
}

audio_publisher_config = {
    "pub_endpoint": f"ipc:///tmp/{platform_uuid}_audio_publisher.sock",
    "pub_topic": f"{platform_uuid}_audio_publisher",
    "sample_rate": 16000,
    "channels": 1,
    "hz": 2,
    "dtype": "int16",
}

audio_writer_config = {
    "sub_endpoint": f"ipc:///tmp/{platform_uuid}_audio_publisher.sock",
    "sub_topic": f"{platform_uuid}_audio_publisher",
    "write_location": "/home/pi/audio_writer/data/",
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

detector_based_deleter_config = {
    "detector_name": f"{platform_uuid}_yolo11m_person_detection",
    "detector_endpoint": f"ipc:///tmp/{platform_uuid}_yolo11m_person_detection.sock",
    "files_location": "/home/pi/h264_writer/data/",
    "h264_writer_topic": f"{platform_uuid}_h264_writer",
    "h264_writer_endpoint": f"ipc:///tmp/{platform_uuid}_h264_writer.sock",
    "seconds_after_keep": 20,
    "seconds_before_keep": 20,
}