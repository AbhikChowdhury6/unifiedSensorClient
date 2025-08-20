instance_name = "testpi"



bme680_sd = {
  "class_name": "aBME680",
  "manufacturer": "Bosch",
  "device_name": "bme680",
  "i2c_address": 0x77,
  "sensors": {
    "air_temperature": {
      "debug_lvl": 20,
      "UUID": "XXX",
      "three_words":"XXX",
      "responsible_party": "Abhik",
      "hz": 2**0,
      "status": "disabled",
      "source": "internal",
      "units": "unit_name",
      "data_type": "float",
      "float_rounding_precision": 5,
      "write_location": "persistent",
      "cache_type": "csv",
      "send_type": "json",
      "new_cache_file_interval": "1m",
    },
    "relative_humidity": {
      "debug_lvl": 20,
    },
    "air_pressure": {

    },
    "volatile_organic_compounds": {

    },
  }
}

scd41_sd = {

}

cam0_sd = {
  "debug_lvl": 20,
  "status": "disabled",
  "v4l_cam_index": 0,
  "width": 1920,
  "height": 1080,
  "consumers": {
    "timelapse": {
      "debug_lvl": 20,
      "status": "disabled",
      "hz": 1/16,
      "image_type": "jpeg",
      "quality": 80,
      "width": 1920,
      "height": 1080,
      "cache_type": "bulk",
      "write_location": "persistent",
      "send_type": "bulk",
    },
    "person_detection": {
      "debug_lvl": 20,
      "status": "disabled",
      "hz": 1/16,
      "model": "yolo11m",
      "secs_valid_range": [-32, 32],
    },
    "motion_detection": {
      "debug_lvl": 20,
      "status": "disabled",
      "hz": 1,
      "difference_threshold": 50,
      "secs_valid_range": [-16, 16],
    },
    "blackout_detection": {
      "debug_lvl": 20,
      "status": "enabled",
      "hz": 1,
      "avg_pixel_value_threshold": 50,
      "secs_valid_range": [-16, 16],
    },
    "detection_based_video": {
      "debug_lvl": 20,
    },
  }
}


platform_state = {
  "debug_lvl": 20,
  "UUID":"XXX",
  "three_words":"XXX",
  "responsible_party": "Abhik",
  "platform_instance_name": instance_name,
  "platform_name": "raspberry_pi_5",
  "network_status": "connected",
  "json_cache_syncing_interval": "1s",
  "bulk_cache_syncing_interval": "4s",
  "upload_address": "",
  "json_endpoint": "",
  "bulk_endpoint": "",
  "busses_used": {
    "camera_0": cam0_sd,
    "i2c_1": {
      "debug_lvl": 20,
      "status": "enabled",
      "devices": {
        "bme680": bme680_sd,
        "scd41": scd41_sd,
      }
    },
    "audio_0": {},
  },

}