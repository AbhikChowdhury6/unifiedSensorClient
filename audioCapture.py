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
        self.device = config.get("device", None)  # sounddevice device name/index or None

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
        self._chunk_sequence: int = 0  # Track chunk sequence for timestamp validation
        self._first_chunk_dt: datetime | None = None  # First chunk timestamp for validation

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
        
        # Calculate expected chunk duration
        chunk_duration = frames / float(self.sample_rate)
        expected_interval = 1.0 / self.frame_hz  # Expected time between chunks
        
        # Handle status flags - input overflow is a serious issue
        has_overflow = False
        if status:
            if 'input overflow' in str(status):
                has_overflow = True
                self.l.warning(f"audio callback status: {status} - system cannot keep up with audio capture!")
            else:
                self.l.debug(f"audio callback status: {status}")
        
        # Prefer PortAudio-provided ADC time for drift-free timestamps
        try:
            if self._pa_epoch_utc_base is None and time_info is not None:
                # Map PortAudio currentTime (seconds) to UTC now
                # Use time_info.currentTime which is more stable than inputBufferAdcTime for initial mapping
                now_utc = datetime.now(timezone.utc)
                self._pa_epoch_utc_base = now_utc - timedelta(seconds=time_info.currentTime)
                self.l.debug(f"audio capture: initialized PortAudio epoch base: {self._pa_epoch_utc_base}")
            else:
                self.l.debug(f"audio capture: no time info, using sequence-based timestamp")

            if self._pa_epoch_utc_base is not None and time_info is not None:
                # Use inputBufferAdcTime which represents when the ADC actually captured the start of this buffer
                dt_utc = self._pa_epoch_utc_base + timedelta(seconds=time_info.inputBufferAdcTime)
                
                # Validate timestamp progression on subsequent chunks
                if self._first_chunk_dt is not None:
                    expected_dt = self._first_chunk_dt + timedelta(seconds=self._chunk_sequence * expected_interval)
                    time_diff = (dt_utc - expected_dt).total_seconds()  # Can be negative or positive
                    
                    # If overflow occurred or drift is significant (>150ms), reset our sequence tracking
                    # to match PortAudio's timestamps (which reflect reality when the ADC actually captured the data)
                    # Lower threshold (150ms) allows us to adapt faster to consistent timing issues
                    if has_overflow or abs(time_diff) > 0.15:
                        if has_overflow:
                            self.l.warning(
                                f"audio capture: input overflow detected - resetting timestamp sequence. "
                                f"Previous expected: {expected_dt}, PortAudio says: {dt_utc}, diff: {time_diff*1000:.1f}ms"
                            )
                        else:
                            self.l.debug(
                                f"audio capture: timestamp drift ({time_diff*1000:.1f}ms) - resetting sequence. "
                                f"Previous expected: {expected_dt}, PortAudio says: {dt_utc}"
                            )
                        # Reset sequence tracking to match PortAudio timestamps
                        self._first_chunk_dt = dt_utc
                        self._chunk_sequence = 0
                    elif abs(time_diff) > 0.05:  # Warn on smaller drifts (>50ms) but don't reset
                        self.l.debug(
                            f"audio capture: timestamp drift detected: "
                            f"chunk {self._chunk_sequence}, expected {expected_dt}, got {dt_utc}, "
                            f"diff {time_diff*1000:.1f}ms"
                        )
            else:
                # Fallback: calculate timestamp based on sequence if we have a first chunk
                
                if self._first_chunk_dt is not None:
                    dt_utc = self._first_chunk_dt + timedelta(seconds=self._chunk_sequence * expected_interval)
                    if self._pa_epoch_utc_base is None:
                        self.l.warning(f"audio capture: no time info, using sequence-based timestamp")
                else:
                    # First chunk with no time info - align to start-of-chunk by subtracting buffer duration from now
                    dt_utc = datetime.now(timezone.utc) - timedelta(seconds=chunk_duration)
                    self.l.warning(f"audio capture: no time info on first callback, using fallback timestamp")
                    # Store first chunk timestamp immediately for future sequence-based calculations
                    self._first_chunk_dt = dt_utc
        except Exception as e:
            self.l.error(f"audio capture: error getting timestamp: {e}")
            # Fallback: calculate from sequence if available, otherwise use now
            if self._first_chunk_dt is not None:
                dt_utc = self._first_chunk_dt + timedelta(seconds=self._chunk_sequence * expected_interval)
            else:
                dt_utc = datetime.now(timezone.utc) - timedelta(seconds=chunk_duration)
                # Store first chunk timestamp immediately
                self._first_chunk_dt = dt_utc
        
        # Store first chunk timestamp for validation (if not already stored)
        if self._first_chunk_dt is None:
            self._first_chunk_dt = dt_utc
        
        try:
            # Copy to avoid buffer reuse
            chunk = np.array(indata, copy=True)
            self._queue.put_nowait((dt_utc, chunk))
            self._chunk_sequence += 1
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
            latency='high',  # Use higher latency to reduce overflow chances
        )
        # Reset PortAudio epoch mapping on start (before starting stream)
        self._pa_epoch_utc_base = None
        self._chunk_sequence = 0
        self._first_chunk_dt = None
        self._stream.start()
        device_info = f"device={self.device}" if self.device is not None else "default device"
        self.l.info(
            f"audio stream started: {self.sample_rate} Hz, {self.channels} ch, blocksize {self.blocksize}, "
            f"dtype {self.dtype}, {device_info}"
        )
        # Give the stream a moment to initialize and get first time_info
        # The epoch mapping will be set on first callback

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
                self.l.debug(f"audio capture: queue empty, breaking")
                break
            # Ensure contiguous array for serialization
            if not isinstance(chunk, np.ndarray):
                chunk = np.asarray(chunk)
            if not chunk.flags["C_CONTIGUOUS"]:
                chunk = np.ascontiguousarray(chunk)
            #print(f"audio capture publishing {chunk.shape} to {self.topic}")
            #sys.stdout.flush()
            self.l.trace(f"current time: {datetime.now(timezone.utc)}")
            self.l.trace(f"audio capture publishing {dt_utc} {chunk.shape} to {self.topic}")
            self.pub.send_multipart(ZmqCodec.encode(self.topic, [dt_utc, chunk]))

