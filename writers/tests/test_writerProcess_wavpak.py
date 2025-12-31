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


@pytest.mark.parametrize(
    "debug_lvl, topic, hz, output_hz, output_base, output_module, file_size_check_interval_s_range, additional_output_config", [
    (20, "wavpak_output_test", 1, 1, "wavpak_output_test", "wavpakOutput", (1, 10), {}),
])

def test_writer_wavpak(tmp_path, debug_lvl, topic, hz, output_hz, output_base, output_module, file_size_check_interval_s_range, additional_output_config):
    log_queue = logging.Queue()
    
    writer_args = {
        "debug_lvl": debug_lvl,
        "log_queue": log_queue,
        "topic": topic,
        "hz": hz,
        "output_hz": output_hz,
        "output_base": output_base,
        "output_module": output_module,
        "file_size_check_interval_s_range": file_size_check_interval_s_range,
        "additional_output_config": additional_output_config}
    writer_process = mp.Process(target=writer_process, name="wavpak_output_test_writer-process", kwargs=writer_args)
    writer_process.start()
    assert writer_process.is_alive()

    





