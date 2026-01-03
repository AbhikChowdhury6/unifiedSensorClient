import msgpack
import numpy as np
import zmq
from datetime import datetime, timezone
from typing import Optional
try:
    from zoneinfo import ZoneInfo  # type: ignore
    def _get_zoneinfo(tz_key: Optional[str]):
        if not tz_key:
            return timezone.utc
        try:
            return ZoneInfo(tz_key)
        except Exception:
            return timezone.utc
except Exception:
    # Fallback when zoneinfo isn't available in the environment
    def _get_zoneinfo(tz_key: Optional[str]):
        return timezone.utc


class ZmqCodec:
    """
    Helper to encode/decode Python objects for ZeroMQ multipart messages.
    - dicts, lists, scalars -> msgpack
    - numpy arrays -> raw bytes + shape + dtype
    """

    @staticmethod
    def encode(topic: str, obj):
        """Encode an object into a multipart [topic, ...]"""
        topic_b = topic.encode() if isinstance(topic, str) else topic

        # Use msgpack ExtType to preserve raw numpy arrays and timezone-aware datetimes
        # ExtType codes
        EXT_DATETIME = 1
        EXT_NDARRAY = 2

        def default(obj_to_pack):
            # Datetime -> ExtType with (epoch_ns, tz_key)
            if isinstance(obj_to_pack, datetime):
                dt = obj_to_pack
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                tz_key = getattr(dt.tzinfo, "key", dt.tzname()) or "UTC"
                payload = msgpack.packb((int(dt.timestamp() * 1_000_000_000), tz_key), use_bin_type=True)
                return msgpack.ExtType(EXT_DATETIME, payload)

            # Numpy ndarray -> ExtType with (shape, dtype_str, raw_bytes)
            if isinstance(obj_to_pack, np.ndarray):
                shape = obj_to_pack.shape
                dtype_str = obj_to_pack.dtype.str
                raw = obj_to_pack.tobytes()
                payload = msgpack.packb((shape, dtype_str, raw), use_bin_type=True)
                return msgpack.ExtType(EXT_NDARRAY, payload)

            # Numpy scalar -> convert to Python scalar
            if isinstance(obj_to_pack, np.generic):
                return obj_to_pack.item()

            # Let msgpack handle the rest
            raise TypeError("Unsupported type")

        packed = msgpack.packb(obj, use_bin_type=True, default=default)
        return [topic_b, b"MSGPACK", packed]

    @staticmethod
    def decode(parts):
        """Decode multipart back into (topic, obj)"""
        topic = parts[0].decode()

        if parts[1] == b"NDARRAY":
            raw, shape_b, dtype_b = parts[2], parts[3], parts[4]
            shape = tuple(msgpack.unpackb(shape_b))
            dtype = np.dtype(dtype_b.decode())
            arr = np.frombuffer(raw, dtype=dtype).reshape(shape)
            return topic, arr

        elif parts[1] == b"MSGPACK":
            EXT_DATETIME = 1
            EXT_NDARRAY = 2

            def ext_hook(code, data):
                if code == EXT_DATETIME:
                    epoch_ns, tz_key = msgpack.unpackb(data, raw=False)
                    tz = _get_zoneinfo(tz_key)
                    return datetime.fromtimestamp(epoch_ns / 1_000_000_000, tz=tz)
                if code == EXT_NDARRAY:
                    shape, dtype_str, raw = msgpack.unpackb(data, raw=False)
                    arr = np.frombuffer(raw, dtype=np.dtype(dtype_str)).reshape(tuple(shape))
                    return arr
                return msgpack.ExtType(code, data)

            obj = msgpack.unpackb(parts[2], raw=False, ext_hook=ext_hook)
            return topic, obj

        else:
            raise ValueError(f"Unknown encoding: {parts[1]}")
