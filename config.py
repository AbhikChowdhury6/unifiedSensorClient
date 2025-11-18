import multiprocessing as mp
from datetime import datetime, timezone
import os
from collections import OrderedDict

# this file will evolve based on features
testpi5UUID = "c57d828b-e8d1-433b-ad79-5420d2136d3f"[-8:]
testpi4UUID = "ae24c81b-3817-48d0-a6f8-799ec3dec556"[-8:]

platform_uuid = testpi4UUID

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

picamv3noirwide = "picamV3-sony-imx708-noir-120fov-12MP"
picamv3noir = "picamV3-sony-imx708-noir-80fov-12MP"
picamv3wide = "picamV3-sony-imx708-120fov-12MP"

repoPath = "/home/pi/Documents/"

###########################################Platform Utilities###########################################

def dt_to_fnString(dt, decimal_places=3):
    microseconds = dt.microsecond / 1_000_000
    truncated_microseconds = f"{microseconds:.6f}"[2:2+decimal_places]
    return dt.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S') + \
        f"p{truncated_microseconds}Z"

def dt_to_path(dt, base_path):
    hour_base_path = os.path.join(base_path, dt.astimezone(timezone.utc).strftime("%Y/%m/%d/%H/%M/"))
    os.makedirs(hour_base_path, exist_ok=True)
    return hour_base_path

def fnString_to_dt(s):
    ts_str = s
    if "/" in s:
        ts_str = ts_str.split("/")[-1]
    if "\\" in s:
        ts_str = ts_str.split("\\")[-1]
    if "_" in s: #if it's like a whole file name
        ts_str = ts_str.split("_")[-1]
    if "." in s:#if it has a file extension
        ts_str = ts_str.split(".")[0]
    ts_str = ts_str.replace("p",".")
    return datetime.fromisoformat(ts_str)

logging_process_config = {
    "module_name": "loggingProcess",
    "module_path": "platformUtils.processes.loggingProcess",
    "func_name": "logging_process",
    "short_name": "logging",
    "time_to_shutdown": .1,
    "debug_lvl": 20,
    "logfile_path": "/home/pi/logs/unifiedSensorClient.log",
}

file_uploader_process_config = {
    "module_name": "fileUploader",
    "module_path": "platformUtils.processes.fileUploader",
    "func_name": "file_uploader",
    "short_name": "file-up",
    "time_to_shutdown": .1,
    "debug_lvl": 20,
    "upload_url": "http://192.168.10.36:/upload",
    "upload_retry_interval": 10,
    "subscription_topics": [
        f"{platform_uuid}_csi-0_{picamv3noirwide}_mp4-8fps_540x960_8hz_writer-process",
        f"{platform_uuid}_csi-0_{picamv3noirwide}_mp4-1fps_540x960_p25hz_writer-process",
        f"{platform_uuid}_audio-1_generic_audio-1ch-48kHz_1x24000-int16_2hz_writer-process",
        f"{platform_uuid}_i2c-1-0x76_bosch-bme280_barometric-pressure_pascal_float_1x1_16hz_writer-process",
        f"{platform_uuid}_i2c-1-0x76_bosch-bme280_air-temperature_celsius_float_1x1_1hz_writer-process",
        f"{platform_uuid}_i2c-1-0x76_bosch-bme280_relative-humidity_percent_float_1x1_p25hz_writer-process",
    ],
    "time_till_ready": 20, # this has to be longer than the delete process time before
    "data_dir": "/home/pi/data/upload/",
}

# connection_check_process_config = {
#     "module_name": "connectionChecker",
#     "module_path": "platformUtils.processes.connectionChecker",
#     "func_name": "connection_check",
#     "short_name": "check",
#     "time_to_shutdown": .1,
#     "debug_lvl": 20,
#     "pub_topic": f"{platform_uuid}_connection_check",
#     "pub_endpoint": f"ipc:///tmp/{platform_uuid}_connection_check.sock",
#     "interval_seconds": 1,
#     "states": ["offline", "hotspot", "home-wifi"],
#     "ssids": {"hotspot": "chowderphone", "home-wifi": "snet24"},
# }

# pigpio_toggle_buttons_process_config = {
#     "module_name": "pigpioButtons",
#     "module_path": "platformUtils.processes.pigpioButtons",
#     "func_name": "pigpio_buttons",
#     "short_name": "buttons",
#     "time_to_shutdown": .1,
#     "debug_lvl": 20,
#     "button_sense_pins": [[20, "low"], [12, "low"], [7, "high"]],
#     "set_high_pins": [21, 16],
#     "set_low_pins": [],
#     "button_message_map": {
#         17: [[['d', 'video']], [['e', 'video']]],
#         27: [[['d', 'audio']], [['e', 'audio']]],
#         26: [
#             [['e', 'yolo'], ['e', 'del'], ['d', "motion"], ['d', "dark"]], # yolo only
#             [['d', 'yolo'], ['e', 'del'], ['e', 'motion'], ['d', 'dark']], # motion only
#             [['d', 'yolo'], ['e', 'del'], ['d', 'motion'], ['e', 'dark']], # dark only
#             [['d', 'yolo'], ['d', 'del'], ['d', 'motion'], ['d', 'dark']], # off
#         ],
#     },
#     "button_endpoint": f"ipc:///tmp/control.sock",
# }

# led_controller_process_config = {
#     "module_name": "ledController",
#     "module_path": "platformUtils.processes.ledController",
#     "func_name": "led_controller",
#     "short_name": "led",
#     "time_to_shutdown": .1,
#     "debug_lvl": 20,
#     "pub_topic": "control",
#     # for requests to main, publish to the dedicated requests endpoint
#     "pub_endpoint": zmq_control_requests_endpoint,
#     "states": {0 : {(255, 0, 0): set([(1, 'video')]), (0, 0, 0): set([(0, 'video')])},
#                1 : {(0, 255, 0): set([(1, 'audio')]), (0, 0, 0): set([(0, 'audio')])},
#                2 : {(255, 0, 0): set([(1, 'yolo'), (1, 'del'), (0, "motion"), (0, "dark")]), # yolo only
#                     (0, 255, 0): set([(0, 'yolo'), (1, 'del'), (1, 'motion'), (0, 'dark')]), # motion only
#                     (0, 0, 255): set([(0, 'yolo'), (1, 'del'), (0, 'motion'), (1, 'dark')]), # dark only
#                     (0, 0, 0): set([(0, 'yolo'), (0, 'del'), (0, 'motion'), (0, 'dark')]), # off
#                 },
#     },
# }

###########################################Platform Sensors###########################################

file_writer_process_info = {
    "module_name": "writerProcess",
    "module_path": "writers.processes.writerProcess",
    "func_name": "writer_process",
    "persist_location": "/home/pi/data/persist/",
    "temp_write_location": "/home/pi/data/temp/",
    "output_write_location": "/home/pi/data/upload/",
    "target_file_size": 10 * 1024 * 1024, #10MB
}

file_output_infos = {
    "audioOutput": {
        "module_name": "audioOutput",
        "module_path": "writers.audioOutput",
        "func_name": "audio_output",
    },
    "wavpakOutput": {
        "module_name": "wavpakOutput",
        "module_path": "writers.wavpakOutput",
        "func_name": "wavpak_output",
    },
    "videoOutput": {
        "module_name": "videoOutput",
        "module_path": "writers.videoOutput",
        "func_name": "video_output",
    },
}

i2c_controller_process_config = {
    "module_name": "i2cController",
    "module_path": "sensors.processes.i2cController",
    "func_name": "i2c_controller",
    "short_name": "i2c",
    "time_to_shutdown": .1,
    "platform_uuid": platform_uuid,
    "bus_number": 1,
    "debug_lvl": 5,
    "device_class_loc": repoPath + "unifiedSensorClient/sensors/i2cDeviceClasses/",
    "devices": [
        {   
            "module_name": "abme280",
            "class_name": "aBME280",
            "module_path": "sensors.i2cDeviceClasses.abme280",
            "device_name": "bosch-bme280",
            "bus_location": "i2c-1-0x76",
            "address": 0x76,
            "debug_lvl": 5,
            "sensors_config": [
                {
                    "sensor_type": "barometric-pressure",
                    "units": "pascal",
                    "data_type": "float",
                    "shape": "1x1",
                    "hz": 16,
                    "topic": f"{platform_uuid}_i2c-1-0x76_bosch-bme280_barometric-pressure_pascal_float_1x1_16hz",
                    "debug_lvl": 10,
                    "file_writer_config": {
                        "output_module": "wavpakOutput",
                        "output_hz": 16,
                        #the change from topic is drop the data shape time dimension
                        "file_size_check_interval_s_range": (30, 60),
                        "output_base": f"{platform_uuid}_i2c-1-0x76_bosch-bme280_barometric-pressure_pascal_float_1_16hz",
                    },
                },
                {
                    "sensor_type": "air-temperature",
                    "units": "celsius",
                    "data_type": "float",
                    "shape": "1x1",
                    "hz": 1,
                    "topic": f"{platform_uuid}_i2c-1-0x76_bosch-bme280_air-temperature_celsius_float_1x1_1hz",
                    "debug_lvl": 20,
                    "file_writer_config": {
                        "output_module": "wavpakOutput",
                        "output_hz": 1,
                        "file_size_check_interval_s_range": (300, 600),
                        "output_base": f"{platform_uuid}_i2c-1-0x76_bosch-bme280_air-temperature_celsius_float_1_1hz",
                    },
                },
                {
                    "sensor_type": "relative-humidity",
                    "units": "percent",
                    "data_type": "float",
                    "shape": "1x1",
                    "hz": .25,
                    "topic": f"{platform_uuid}_i2c-1-0x76_bosch-bme280_relative-humidity_percent_float_1x1_0p25hz",
                    "debug_lvl": 20,
                    "file_writer_config": {
                        "output_module": "wavpakOutput",
                        "output_hz": .25,
                        "file_size_check_interval_s_range": (300, 600),
                        "output_base": f"{platform_uuid}_i2c-1-0x76_bosch-bme280_relative-humidity_percent_float_1_0p25hz",
                    },
                },
            ],
        }
    ]
}


audio_controller_process_1_config = {
    "module_name": "audioController",
    "module_path": "sensors.processes.audioController",
    "func_name": "audio_controller",
    "short_name": "audio",
    "time_to_shutdown": .6,
    "debug_lvl": 5,
    #format is platformUUID_busLocation_deviceName_sensorType_units_dataType_shape_hz
    "platform_uuid": platform_uuid,
    "bus_location": "audio-1",
    "device_name": "generic",
    "sensor_type": "sound",
    "units": "int16",
    "data_type": "int",
    "shape": "8000x1",
    "hz": 2,
    "topic": f"{platform_uuid}_audio-1_generic_sound_int16_int_8000x1_2hz",
    
    "sample_rate": 48000,
    "subsample_ratio": 3,

    "channels": 1,
    "dtype": "int16",
    "device": 1,  # USB PnP Sound Device: Audio (hw:3,0) - supports timing
    "file_writer_config": {
        "output_module": "audioOutput",
        "output_hz": 16000,
        "output_base": f"{platform_uuid}_audio-1_generic_audio_int16_int_1_16000hz",
    },
}

#c3dec556_csi-0_picamV3-sony-imx708-noir-120fov-12MP_image_BGR_uint8_1x960x540x3_8hz
camera_topic = f"{platform_uuid}_csi-0_{picamv3noirwide}_image_BGR_uint8_1x960x540x3_8hz"
camera_endpoint = f"ipc:///tmp/{camera_topic}.sock"

video_controller_process_1_config = {
    "module_name": "videoController",
    "module_path": "sensors.processes.videoController",
    "func_name": "video_controller",
    "short_name": "video",
    "time_to_shutdown": .25,
    "debug_lvl": 20,
    
    "camera_class_loc": repoPath + "unifiedSensorClient/sensors/videoDeviceClasses/",
    "camera_module_name": "piCamera",
    "camera_class_name": "PiCamera",
    "camera_module_path": "sensors.videoDeviceClasses.piCamera",
    
    "platform_uuid": platform_uuid,
    "bus_location": "csi-0",
    "device_name": picamv3noirwide,
    "sensor_type": "image",
    "units": "BGR",
    "data_type": "uint8",
    "shape": "1x960x540x3",
    "hz": 8,
    "file_writer_config": {},
    "topic": camera_topic,

    "camera_index": 0,
    "camera_width": 1920,
    "camera_height": 1080,
    "subsample_ratio": 2,
    "format": "RGB888",
    "flip_vertical": True,
    "timestamp_images": True,
}


# gps_capture_process_config = {
#     "module_name": "gpsCapture",
#     "module_path": "sensors.processes.gpsCapture",
#     "func_name": "gps_capture",
#     "short_name": "gps",
#     "time_to_shutdown": 1,
#     "debug_lvl": 20,
#     "baudrate": 9600,
#     "timeout": 10,
#     "update_hz": 1,
#     "serial_port": "ttyUSB0",
#     "baudrate": 9600,
#     "timeout": 10,
#     "update_hz": 1,
#     "pub_topic_3dFix": f"{platform_uuid}_ttyUSB0_cdtopTech-PA1616S_gps3dFix",
#     "pub_endpoint_3dFix": f"ipc:///tmp/{platform_uuid}_ttyUSB0_adafruit_PA1616S_gps3dFix.sock",
#     "pub_topic_speed": f"{platform_uuid}_ttyUSB0_cdtop-tech_PA1616S_gpsSpeed",
#     "pub_endpoint_speed": f"ipc:///tmp/{platform_uuid}_ttyUSB0_cdtop-tech_PA1616S_gpsSpeed.sock",
#     "pub_topic_epe": f"{platform_uuid}_ttyUSB0_cdtop-tech_PA1616S_gpsEPEP",
#     "pub_endpoint_epe": f"ipc:///tmp/{platform_uuid}_ttyUSB0_cdtop-tech_PA1616S_gpsEPEP.sock",
# }

###########################################Platform Data Writers###########################################

sqlite_writer_write_location = "/home/pi/data/temp/sqlite_writer/"

sqlite_writer_process_config = {
    "module_name": "sqliteWriter",
    "module_path": "writers.processes.sqliteWriter",
    "func_name": "sqlite_writer",
    "short_name": "sqlite",
    "time_to_shutdown": .1,
    "debug_lvl": 20,
    "write_location": sqlite_writer_write_location,
    "subscription_endpoints": [
#        f"ipc:///tmp/{platform_uuid}_i2c-1-0x76_bosch-bme280_relative-humidity_percent_float.sock",
        f"ipc:///tmp/{platform_uuid}_yolo11m_person_detection.sock",
#        f"ipc:///tmp/{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gps3dFix.sock",
#        f"ipc:///tmp/{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gpsSpeed.sock",
#        f"ipc:///tmp/{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gpsEPEP.sock",
    ],
    "subscription_topics": [
#        f"{platform_uuid}_i2c-1-0x76_bosch-bme280_relative-humidity_percent_float",
        f"{platform_uuid}_yolo11m_person_detection",
#        f"{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gps3dFix",
#        f"{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gpsSpeed",
#        f"{platform_uuid}_serial_ttyUSB0_cdtop-tech_PA1616S_gpsEPEP",
    ],
}



# writer_process_configs = {
#     "module_name": "writerProcess",
#     "module_path": "writers.processes.writerProcess",
#     "func_name": "writer_process",
#     "temp_write_location": "/home/pi/data/temp/",
#     "completed_write_location": "/home/pi/data/upload/",
#     "target_file_size": 10 * 1024 * 1024, #10MB
#     "file_size_check_interval_s_range": (30, 60),
#     "writers": {
#         "audio": {
#             "output_module": "audioOutput",
#             "output_module_path": "writers.audioOutput",
#             "output_class": "audio_output",

#             "configs": [
#                 {
#                 "topic": f"{platform_uuid}_audio-1_generic_audio-1ch-16kHz_1x8000-int16",
#                 "process_name": f"{platform_uuid}_audio-1_generic_audio-1ch-16kHz_1x8000-int16_writer-process",
#                 "expected_hz": 2,
#                 "bitrate": "16k",
#                 "sample_rate": 16000,
#                 }
#             ],
#         },
#     }
# }  


detector_timelapse_writer_process_config = {
    "module_name": "detectorTimelapseWriter",
    "module_path": "writers.processes.detectorTimelapseWriter",
    "func_name": "detector_timelapse_writer",
    "short_name": "detector_timelapse",
    "time_to_shutdown": .1,
    "debug_lvl": 5,
    "cache_location": "/home/pi/camera_cache/",
    "temp_file_location": "/home/pi/data/temp/",
    "completed_write_location_base": "/home/pi/data/upload/",
    "target_file_size": 10 * 1024 * 1024, #10MB
    "time_before_seconds": 16,
    "time_after_seconds": 16,
    
    "camera_endpoint": camera_endpoint,
    "camera_topic": camera_topic,
    
    "detector_endpoints": [
        f"ipc:///tmp/{platform_uuid}_yolo11m_person_detection.sock",
    ],
    "detector_topics": [
        f"{platform_uuid}_yolo11m_person_detection",
    ],

    "full_speed_output_config": {
        "output_base": f"{platform_uuid}_csi-0_{picamv3noirwide}_mp4-960x540x3-8hz",
        "hz": 8,
        "file_size_check_interval_s_range": (5, 10),
        "camera_width": 960,
        "camera_height": 540,
        "gop_interval": 256,
        "preset": "ultrafast",
        "crf": 23,

        "codec": "libx264",
        "pix_fmt": "yuv420p",
        "x264_params": "scenecut=0",
    },
    
    "timelapse_output_config": {
        "output_base": f"{platform_uuid}_csi-0_{picamv3noirwide}_mp4-960x540x3-p25hz",
        "hz": .25,
        "file_size_check_interval_s_range": (30, 60),
        "camera_width": 960,
        "camera_height": 540,
        "gop_interval": 1024,
        "preset": "slow",
        "crf": 23,

        "codec": "libx264",
        "pix_fmt": "yuv420p",
        "x264_params": "scenecut=0",
    },
}

# # note all sensors are floats and are in units standard for the sensor
# person_mp4_writer_process_config = {
#     "module_name": "personMp4Writer",
#     "module_path": "writers.processes.personMp4Writer",
#     "func_name": "person_mp4_writer",
#     "short_name": "person_mp4",
#     "time_to_shutdown": .1,
#     "debug_lvl": 20,
#     "completed_full_speed_write_location_base": "/home/pi/data/upload/person_mp4_writer_fs/",
#     "completed_timelapse_write_location_base": "/home/pi/data/upload/person_mp4_writer_tl/",
#     "timelapse_interval_seconds": 4,
#     "cache_location": "/home/pi/camera_cache/",
#     "temp_file_location": "/home/pi/data/temp/person_mp4_writer_temp/",
#     "full_speed_file_base": f"{platform_uuid}_csi-0_{picamv3noirwide}_mp4-8fps",
#     "timelapse_file_base": f"{platform_uuid}_csi-0_{picamv3noirwide}_mp4-p25fps",
# }

# audio_writer_process_config = {
#     "module_name": "audioWriter",
#     "module_path": "writers.processes.audioWriter",
#     "func_name": "audio_writer",
#     "short_name": "opus",
#     "time_to_shutdown": .1,
#     "debug_lvl": 10,

#     "sub_endpoint": f"ipc:///tmp/{platform_uuid}_audio-1_generic_audio-1ch-48kHz_1x24000-int16.sock",
#     "sub_topic": f"{platform_uuid}_audio-1_generic_audio-1ch-48kHz_1x24000-int16",

#     "persist_location": "/home/pi/data/temp/audio_writer_cache/",
#     "temp_write_location": "/home/pi/data/temp/audio_writer/",
#     "completed_write_location": "/home/pi/data/upload/audio_writer/",
#     "target_file_size": 10 * 1024 * 1024, #10MB
#     "extension": ".opus",
#     "expected_hz": 2,
#     "file_size_check_interval_s_range": (30, 60),
    
#     "bitrate": "16k",
#     "sample_rate": 48000,
#     "channels": 1,
#     "application": "audio",
#     "frame_duration_ms": 40, #this is the frame duration for the opus encoder
# }

###########################################Platform Analyzers###########################################

yolo_person_detector_process_config = {
    "module_name": "yoloPersonDetector",
    "module_path": "analyzers.processes.yoloPersonDetector",
    "func_name": "yolo_person_detector",
    "short_name": "yolo",
    "time_to_shutdown": 3,
    "debug_lvl": 10,
    "camera_topic": camera_topic,
    "camera_endpoint": camera_endpoint,
    "pub_endpoint": f"ipc:///tmp/{platform_uuid}_yolo11m_person_detection.sock",
    "pub_topic": f"{platform_uuid}_yolo11m_person_detection",
    "model": "yolo11n",
    "confidence_threshold": 0.5,
    "nms_threshold": 0.5,
    "interval_seconds": 4,
    "verbose": True,
}

# is_dark_detector_process_config = {
#     "module_name": "isDarkDetector",
#     "module_path": "analyzers.processes.isDarkDetector",
#     "func_name": "is_dark_detector",
#     "short_name": "dark",
#     "time_to_shutdown": .1,
#     "debug_lvl": 20,
#     "pub_topic": f"{platform_uuid}_is_dark_detector",
#     "pub_endpoint": f"ipc:///tmp/{platform_uuid}_is_dark_detector.sock",
#     "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
#     "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
#     "threshold": 0.5,
#     "interval_seconds": 1,
# }

# motion_detector_process_config = {
#     "module_name": "motionDetector",
#     "module_path": "analyzers.processes.motionDetector",
#     "func_name": "motion_detector",
#     "short_name": "motion",
#     "time_to_shutdown": .1,
#     "debug_lvl": 10,
#     "pub_topic": f"{platform_uuid}_motion_detector",
#     "pub_endpoint": f"ipc:///tmp/{platform_uuid}_motion_detector.sock",
#     "camera_name": f"{platform_uuid}_csi-0_{picamv3noirwide}",
#     "camera_endpoint": f"ipc:///tmp/{platform_uuid}_csi-0_{picamv3noirwide}.sock",
#     "threshold": 50,
#     "interval_seconds": 1,
# }

###########################################Platform Processes###########################################

all_process_configs = {
    "sqlite": [1, sqlite_writer_process_config],
    "i2c": [1, i2c_controller_process_config],
    "video": [1, video_controller_process_1_config],
    "detector_timelapse": [1, detector_timelapse_writer_process_config],
    "yolo": [1, yolo_person_detector_process_config],
#    "audio": [1, audio_controller_process_config],
#    "opus": [1, audio_writer_process_config],
#    "dark": [0, is_dark_detector_process_config],
#    "motion": [0, motion_detector_process_config],
#    "buttons": pigpio_toggle_buttons_process_config,
#    "led": [0, led_controller_process_config],
#    "file-up": [0, file_uploader_process_config],
}