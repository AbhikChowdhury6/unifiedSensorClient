from writers.wavpakOutput import wavpak_output
import multiprocessing as mp
import pytest
import logging
from logging.handlers import QueueListener

#so what am I going to be doing here?
#so the pipeline will be that I will
# - I will have a table of data where the rows are my test cases
#  - initalize an object
# - call open on the first value
# - I could check that the file opened in the right spot, nahh we can do that later

from writers.processes.writerProcess import writer_process
from config import zmq_control_endpoint
import pandas as pd
import numpy as np
import os
from datetime import datetime, timezone
import zmq
from platformUtils.zmq_codec import ZmqCodec
import time
import subprocess


def generate_wavpak_test_data(data_loc, data_hz, start_time, duration_seconds):
    files = os.listdir(data_loc)
    data = pd.concat([pd.read_parquet(os.path.join(data_loc, f)) for f in files])
    num_samples = duration_seconds * data_hz
    # Use integer nanoseconds per sample to avoid pandas freq parsing issues
    ns_per_sample = int(round(1e9 / data_hz))
    timestamps = pd.date_range(start=start_time, periods=num_samples, freq=pd.to_timedelta(ns_per_sample, unit="ns"))
    data = data.iloc[:num_samples].reset_index(drop=True).values.squeeze()
    return pd.DataFrame({'timestamp': timestamps, 'data': data})

@pytest.mark.parametrize(
    "debug_lvl, topic, hz, output_hz, file_size_check_interval_s_range, additional_output_config", [
    (5, "wavpak_output_test", 16, 16, (1, 10), 
    {"input_dtype_str": "float32", "output_dtype_str": "int16", "float_bits": 8, "bits": 16, "sign": "s", "channels": 1}),
])

def test_writer_wavpak(tmp_path, debug_lvl, topic, hz, output_hz, file_size_check_interval_s_range, additional_output_config):
    log_queue = mp.Queue()

    file_writer_process_info = {
        "module_name": "writerProcess",
        "module_path": "writers.processes.writerProcess",
        "func_name": "writer_process",
        "persist_location": str(tmp_path / "persist"),
        "temp_write_location": str(tmp_path / "temp"),
        "output_write_location": str(tmp_path / "upload"),
        "platform_uuid": "test",
        "target_file_size": 64 * 1024 * 1024, #64MB
    }
    
    output_info = {
        "wavpakOutput": {
            "module_name": "wavpakOutput",
            "module_path": "writers.wavpakOutput",
            "func_name": "wavpak_output",
        }
    }
    
    output_module = "wavpakOutput"
    
    #we are going to spin up a writer process
    writer_process_args = {
        "log_queue": log_queue,
        "topic": topic,
        "msg_hz": hz,
        "output_hz": hz,
        "output_base": topic,
        "output_module": output_module,
        "file_size_check_interval_s_range": file_size_check_interval_s_range,
        "debug_lvl": debug_lvl,
        "file_writer_process_info": file_writer_process_info,
        "output_info": output_info,
        "additional_output_config": additional_output_config}
    
    
    print("starting writer process")
    # start a QueueListener to print worker logs during the test
    fmt = '[%(asctime)s] [%(name)s] [%(funcName)s] [%(levelname)s] [%(lineno)d] %(message)s'
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(fmt))
    stream_handler.setLevel(getattr(logging, "TRACE", logging.DEBUG))
    log_listener = QueueListener(log_queue, stream_handler, respect_handler_level=True)
    log_listener.start()

    writer_proc = mp.Process(target=writer_process, name="wavpak_output_test_writer-process", kwargs=writer_process_args)
    writer_proc.start()
    time.sleep(1)
    assert writer_proc.is_alive()

    #let's get our publishing going
    pub_socket = zmq.Context().socket(zmq.PUB)
    pub_socket.bind(f"ipc:///tmp/{topic}.sock")

    #now lets get our data going
    test_data_folder = "/home/chowder/Documents/unifiedSensorClient/writers/tests/test_humidity_data/"
    data = generate_wavpak_test_data(test_data_folder, hz, datetime(2026, 1, 7, 0, 0, 0, 0, timezone.utc), 1 * 1 * 10)
    start_dt = data['timestamp'].iloc[0]
    end_dt = data['timestamp'].iloc[-1]

    print("starting data publication")
    print("expected number of messages: ", len(data))
    print("expected duration: ", len(data) / hz)

    #now I would like to publish each row, sleeping for the appropriate amount of time
    for index, row in data.iterrows():
        pub_socket.send_multipart(ZmqCodec.encode(topic, [row['timestamp'], np.array([row['data']])]))
        time.sleep(1/hz)

    print("closing writer process")
    #now lets close the writer process
    control_pub = zmq.Context().socket(zmq.PUB)
    control_pub.bind(zmq_control_endpoint)
    # small sleep to allow bind
    time.sleep(0.05)
    control_pub.send_multipart(ZmqCodec.encode("control", ["exit_all"]))
    writer_proc.join(timeout=10)
    # stop log listener once the worker has exited (or timeout elapsed)
    log_listener.stop()
    time.sleep(10)
    assert not writer_proc.is_alive()

    #list the files in the temp write location
    temp_write_location = file_writer_process_info["temp_write_location"]
    files = os.listdir(temp_write_location)
    print(files)
    
    #now lets check that the data is in the file
    assert os.path.exists(tmp_path / f"{topic}_{start_dt.strftime('%Y%m%dT%H%M%Sp%fZ')}_{end_dt.strftime('%Y%m%dT%H%M%Sp%fZ')}.wv")

    #now lets check that the data is in the file
    wvunpack_cmd = ["wvunpack", "--raw", tmp_path / f"{topic}_{start_dt.strftime('%Y%m%dT%H%M%Sp%fZ')}_{end_dt.strftime('%Y%m%dT%H%M%Sp%fZ')}.wv", "-o", "-"]
    result = subprocess.run(wvunpack_cmd, capture_output=True, check=True)
    raw_data = result.stdout
    data_array = np.frombuffer(raw_data, dtype=getattr(np, additional_output_config["output_dtype_str"]))
    #assert all values are equal
    assert np.all(data_array == data['data'].values)









