import sys
import queue
from datetime import datetime, timezone, timedelta

import numpy as np
import sounddevice as sd
import zmq
import logging

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec


class AudioCapture:
    def __init__(self, config: dict):
        self.l = logging.getLogger(config["short_name"])
        self.l.setLevel(config["debug_lvl"])
        self.l.debug("audio capture class initializing")
        self.config = config

        self.sample_rate = int(config["sample_rate"])
        self.channels = int(config["channels"])
        self.frame_hz = float(config["hz"])
        self.blocksize = int(round(self.sample_rate / self.frame_hz))
        self.dtype = config["dtype"]  # "int16" or "float32"
        self.device = config["device"]  # sounddevice device name/index or None

        self.topic = config["pub_topic"]
        self.endpoint = config["pub_endpoint"]

        self.ctx = zmq.Context()
        self.pub = self.ctx.socket(zmq.PUB)
        self.pub.bind(self.endpoint)
        self.l.info(f"audio capture publishing to {self.topic} at {self.endpoint}")
        sys.stdout.flush()

        self._queue: queue.Queue = queue.Queue(maxsize=8)
        self._stream = None
        self._next_chunk_ts_utc: datetime | None = None
        self._pa_epoch_utc_base: datetime | None = None  # maps PortAudio time to UTC

        self._enabled = False

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def is_enabled(self):
        return self._enabled

    def _callback(self, indata, frames, time_info, status):
        if not self._enabled:
            return
        if status:
            self.l.debug(f"audio callback status: {status}")
        # Prefer PortAudio-provided ADC time for drift-free timestamps
        try:
            if self._pa_epoch_utc_base is None and time_info is not None:
                # Map PortAudio currentTime (seconds) to UTC now
                self._pa_epoch_utc_base = datetime.now(timezone.utc) - timedelta(seconds=time_info.currentTime)
            if self._pa_epoch_utc_base is not None and time_info is not None:
                dt_utc = self._pa_epoch_utc_base + timedelta(seconds=time_info.inputBufferAdcTime)
            else:
                # Fallback: align to start-of-chunk by subtracting buffer duration from now
                dt_utc = datetime.now(timezone.utc) - timedelta(seconds=frames / float(self.sample_rate))
        except Exception:
            dt_utc = datetime.now(timezone.utc)
        try:
            # Copy to avoid buffer reuse
            chunk = np.array(indata, copy=True)
            self._queue.put_nowait((dt_utc, chunk))
        except queue.Full:
            # Drop if consumer is behind
            pass

    def start(self):
        if self._stream is not None:
            return
        # Validate sample rate and fall back to common supported rates if needed
        #desired_sr = self.sample_rate
        # candidates = [desired_sr, 48000, 32000, 16000, 8000] #all perfectly divisible by 64
        # chosen_sr = None
        # for sr in candidates:
        #     try:
        #         sd.check_input_settings(device=self.device, channels=self.channels, samplerate=sr, dtype=self.dtype)
        #         chosen_sr = sr
        #         break
        #     except Exception:
        #         continue
        # if chosen_sr is None:
        #     raise RuntimeError("audio: no supported sample rate found for the selected device")

        # if chosen_sr != self.sample_rate:
        #     self.l.warning(f"audio: requested {self.sample_rate} Hz not supported, using {chosen_sr} Hz")
        #     self.sample_rate = chosen_sr
        #     self.blocksize = int(round(self.sample_rate / self.frame_hz))

        self._stream = sd.InputStream(
            device=self.device,
            channels=self.channels,
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
            dtype=self.dtype,
            callback=self._callback,
        )
        self._stream.start()
        self.l.info(
            "audio stream started: " + str(self.sample_rate) + " Hz, " + str(self.channels) + " ch, blocksize " + str(self.blocksize) + ", dtype " + str(self.dtype)
        )
        # Reset PortAudio epoch mapping on start
        self._pa_epoch_utc_base = None

    def stop(self):
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
            self.l.info("audio stream stopped")
            sys.stdout.flush()

    def publish_pending(self):
        if not self._enabled:
            return
        while True:
            try:
                dt_utc, chunk = self._queue.get_nowait()
            except queue.Empty:
                break
            # Ensure contiguous array for serialization
            if not isinstance(chunk, np.ndarray):
                chunk = np.asarray(chunk)
            if not chunk.flags["C_CONTIGUOUS"]:
                chunk = np.ascontiguousarray(chunk)
            #print(f"audio capture publishing {chunk.shape} to {self.topic}")
            #sys.stdout.flush()
            self.pub.send_multipart(ZmqCodec.encode(self.topic, [dt_utc, chunk]))

