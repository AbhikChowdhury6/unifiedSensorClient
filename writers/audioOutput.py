import sys
import pickle
import os
import subprocess
import threading
from datetime import datetime
repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from config import dt_to_fnString, fnString_to_dt
import logging


class audio_output:
    def __init__(self, config):
        self.config = config
        self.log_name = self.config["topic"] + "_audio-output"
        self.l = logging.getLogger(self.log_name)
        self.l.setLevel(self.config['debug_lvl'])
        self.l.info(self.log_name + " starting")
        self.ff = None
        self.file_name = None
        self.extension = ".opus"
        self.temp_output_location = self.config["temp_write_location"] + self.config["topic"] + "/"
    
    def persist(self, dt, data, path):
        fn = path + dt_to_fnString(dt, 6) + ".pkl"
        pickle.dump(data, open(fn, "wb"))

    def load(self, path):
        return fnString_to_dt(path), pickle.load(open(path, "rb"))

    def open(self, dt: datetime):
        """Spawn ffmpeg to encode PCM from stdin into Opus segments using config.

        Reads all parameters from audio_writer_config for simplicity.
        Returns a subprocess.Popen handle with stdin PIPE for feeding PCM.
        """
        channels = int(self.config["channels"])
        sample_rate = int(self.config["sample_rate"])
        bitrate = str(self.config["bitrate"])
        frame_duration_ms = int(self.config["frame_duration_ms"])
        loglevel = str(self.config["loglevel"])
        sample_fmt = "s16le"
        self.file_name = self.config["topic"] + "_" + dt_to_fnString(dt, 6) + self.extension

        file_name_and_path = self.temp_output_location + self.file_name

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", loglevel,
            "-f", sample_fmt,
            "-ac", str(channels),
            "-ar", str(sample_rate),
            "-i", "pipe:0",
            "-c:a", "libopus",
            "-b:a", bitrate,
            "-frame_duration", str(frame_duration_ms),
            file_name_and_path,
        ]

        #standard error reader and running ffmpeg
        try:
            # Force UTC for strftime in ffmpeg so paths match UTC-based folders
            env = os.environ.copy()
            env["TZ"] = "UTC"
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                bufsize=0, env=env
            )
            self.l.debug(self.log_name + " started ffmpeg: " + " ".join(cmd))

            # Start a background stderr reader for diagnostics
            t = threading.Thread(target=self._stderr_reader, args=(proc,), daemon=True)
            t.start()
            proc._stderr_thread = t  # attach for lifecycle awareness
            self.ff = proc
            self.is_open = True
            return self.file_name
        except FileNotFoundError:
            self.l.error(self.log_name + " ffmpeg not found. Please install ffmpeg.")
            return None
        except Exception as e:
            self.l.error(self.log_name + " failed to start ffmpeg: " + str(e))
            return None


    def _stderr_reader(self, p):
        try:
            for raw in iter(p.stderr.readline, b""):
                line = raw.decode(errors="replace").rstrip()
                if line:
                    self.l.debug(self.log_name + " ffmpeg stderr: " + line)
        except Exception as e:
            self.l.error(self.log_name + " ffmpeg stderr reader error: " + str(e))
        finally:
            self.l.debug(self.log_name + " ffmpeg stderr: [closed]")
    
    def close(self, dt: datetime):
        #close the stdin
        if self.ff.stdin is not None:
            self.ff.stdin.close()
        
        try:
            self.ff.terminate()
            self.ff.wait(timeout=3)
        except Exception as e:
            self.l.error(self.log_name + " failed to terminate ffmpeg: " + str(e))
        try:
            self.ff.kill()
            self.ff.wait(timeout=2)
        except Exception as e:
            self.l.error(self.log_name + " failed to kill ffmpeg: " + str(e))
        self.ff = None

        #rename the file to seal it
        new_fn = self.file_name.replace(self.extension, 
                                        "_" + dt_to_fnString(dt, 6) + self.extension)
        os.rename(self.temp_output_location + self.file_name, 
                  self.temp_output_location + new_fn)
        self.file_name = None
        return new_fn

    def write(self, data):
        self.ff.stdin.write(data)
        
