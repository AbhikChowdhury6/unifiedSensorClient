from writers.wavpakOutput import wavpak_output
import multiprocessing as mp
import pytest
import logging

#so what am I going to be doing here?
#so the pipeline will be that I will
# - I will have a table of data where the rows are my test cases
#  - initalize an object
# - call open on the first value
# - I could check that the file opened in the right spot, nahh we can do that later

from config import file_writer_process_info, file_output_infos
from writers.processes.writerProcess import writer_process
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
    timestamps = pd.date_range(start=start_time, periods=num_samples, freq=f'{1/data_hz}s')
    data = data.iloc[:num_samples].reset_index(drop=True).values.squeeze()
    return pd.DataFrame({'timestamp': timestamps, 'data': data})

@pytest.mark.parametrize(
    "debug_lvl, topic, hz, output_hz, file_size_check_interval_s_range, additional_output_config", [
    (20, "wavpak_output_test", 1, 1, (1, 10), 
    {"input_dtype_str": "float32", "output_dtype_str": "int16", "float_bits": 8, "bits": 16, "sign": "s", "channels": 1}),
])

def test_writer_wavpak(tmp_path, debug_lvl, topic, hz, output_hz, file_size_check_interval_s_range, additional_output_config):
    log_queue = logging.Queue()

    output_module = "wavpakOutput"
    
    #we are going to spin up a writer process
    writer_args = {
        "debug_lvl": debug_lvl,
        "log_queue": log_queue,
        "topic": topic,
        "hz": hz,
        "output_hz": output_hz,
        "output_base": tmp_path,
        "output_module": output_module,
        "file_size_check_interval_s_range": file_size_check_interval_s_range,
        "additional_output_config": additional_output_config}
    writer_process = mp.Process(target=writer_process, name="wavpak_output_test_writer-process", kwargs=writer_args)
    writer_process.start()
    time.sleep(1)
    assert writer_process.is_alive()

    #let's get our publishing going
    pub_socket = zmq.Context().socket(zmq.PUB)
    pub_socket.bind(f"ipc:///tmp/{topic}.sock")

    #now lets get our data going
    test_data_folder = "/home/chowder/Documents/unifiedSensorClient/writers/tests/test_humidity_data/"
    data = generate_wavpak_test_data(test_data_folder, hz, datetime(2026, 1, 7, 0, 0, 0, 0, timezone.utc), 1 * 1 * 60)
    start_dt = data['timestamp'].iloc[0]
    end_dt = data['timestamp'].iloc[-1]

    #now I would like to publish each row, sleeping for the appropriate amount of time
    for index, row in data.iterrows():
        pub_socket.send_multipart([topic.encode(), ZmqCodec.encode(topic, [row['timestamp'], row['data']])])
        time.sleep(1/hz)

    #now lets close the writer process
    pub_socket.send_multipart([topic.encode(), ZmqCodec.encode(topic, ["exit", writer_process.name])])
    writer_process.join()
    time.sleep(1)
    assert not writer_process.is_alive()

    #now lets check that the data is in the file
    assert os.path.exists(tmp_path / f"{topic}_{start_dt.strftime('%Y%m%dT%H%M%Sp%fZ')}_{end_dt.strftime('%Y%m%dT%H%M%Sp%fZ')}.wv")

    #now lets check that the data is in the file
    wvunpack_cmd = ["wvunpack", "--raw", tmp_path / f"{topic}_{start_dt.strftime('%Y%m%dT%H%M%Sp%fZ')}_{end_dt.strftime('%Y%m%dT%H%M%Sp%fZ')}.wv", "-o", "-"]
    result = subprocess.run(wvunpack_cmd, capture_output=True, check=True)
    raw_data = result.stdout
    data_array = np.frombuffer(raw_data, dtype=getattr(np, additional_output_config["output_dtype_str"]))
    #assert all values are equal
    assert np.all(data_array == data['data'].values)









