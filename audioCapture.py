import sys
import queue
from datetime import datetime, timezone

import numpy as np
import sounddevice as sd
import zmq


repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")
from zmq_codec import ZmqCodec


class AudioCapture:
    def __init__(self, config: dict):
        self.config = config

        self.sample_rate = int(config.get("sample_rate", 16000))
        self.channels = int(config.get("channels", 1))
        self.frame_hz = float(config.get("hz", 16))
        self.blocksize = max(1, int(round(self.sample_rate / self.frame_hz)))
        self.dtype = config.get("dtype", "int16")  # "int16" or "float32"
        self.device = config.get("device", None)  # sounddevice device name/index or None

        self.topic = config["pub_topic"]
        self.endpoint = config["pub_endpoint"]

        self.ctx = zmq.Context()
        self.pub = self.ctx.socket(zmq.PUB)
        self.pub.bind(self.endpoint)
        print(f"audio capture publishing to {self.topic} at {self.endpoint}")
        sys.stdout.flush()

        self._queue: queue.Queue = queue.Queue(maxsize=8)
        self._stream = None

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
            print(f"audio callback status: {status}")
            sys.stdout.flush()
        ts = datetime.now(timezone.utc)
        try:
            # Copy to avoid buffer reuse
            chunk = np.array(indata, copy=True)
            self._queue.put_nowait((ts, chunk))
        except queue.Full:
            # Drop if consumer is behind
            pass

    def start(self):
        if self._stream is not None:
            return
        # Validate sample rate and fall back to common supported rates if needed
        desired_sr = self.sample_rate
        candidates = [desired_sr, 48000, 44100, 32000, 22050, 16000, 8000]
        chosen_sr = None
        for sr in candidates:
            try:
                sd.check_input_settings(device=self.device, channels=self.channels, samplerate=sr, dtype=self.dtype)
                chosen_sr = sr
                break
            except Exception:
                continue
        if chosen_sr is None:
            raise RuntimeError("audio: no supported sample rate found for the selected device")

        if chosen_sr != self.sample_rate:
            print(f"audio: requested {self.sample_rate} Hz not supported, using {chosen_sr} Hz")
            sys.stdout.flush()
            self.sample_rate = chosen_sr
            self.blocksize = max(1, int(round(self.sample_rate / self.frame_hz)))

        self._stream = sd.InputStream(
            device=self.device,
            channels=self.channels,
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
            dtype=self.dtype,
            callback=self._callback,
        )
        self._stream.start()
        print(
            f"audio stream started: {self.sample_rate} Hz, {self.channels} ch, blocksize {self.blocksize}, dtype {self.dtype}"
        )
        sys.stdout.flush()

    def stop(self):
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
            print("audio stream stopped")
            sys.stdout.flush()

    def publish_pending(self):
        if not self._enabled:
            return
        while True:
            try:
                ts, chunk = self._queue.get_nowait()
            except queue.Empty:
                break
            # Ensure contiguous array for serialization
            if not isinstance(chunk, np.ndarray):
                chunk = np.asarray(chunk)
            if not chunk.flags["C_CONTIGUOUS"]:
                chunk = np.ascontiguousarray(chunk)
            print(f"audio capture publishing {chunk.shape} to {self.topic}")
            sys.stdout.flush()
            self.pub.send_multipart(ZmqCodec.encode(self.topic, [ts, chunk]))

