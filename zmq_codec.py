import msgpack
import numpy as np
import zmq
from datetime import datetime, timezone


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

        # Helper to convert objects into msgpack-safe structures
        def to_packable(value):
            # Datetime -> epoch nanoseconds integer (UTC)
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    # Assume naive datetimes are UTC
                    value = value.replace(tzinfo=timezone.utc)
                return int(value.timestamp() * 1_000_000_000)

            # Numpy ndarray -> Python nested lists
            if isinstance(value, np.ndarray):
                return value.tolist()

            # Numpy scalar -> Python scalar
            if isinstance(value, np.generic):
                return value.item()

            # Lists/Tuples -> recurse
            if isinstance(value, (list, tuple)):
                return [to_packable(v) for v in value]

            # Dicts -> recurse on values (keys left as-is)
            if isinstance(value, dict):
                return {k: to_packable(v) for k, v in value.items()}

            return value

        packable_obj = to_packable(obj)
        return [topic_b, b"MSGPACK", msgpack.packb(packable_obj, use_bin_type=True)]

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
            obj = msgpack.unpackb(parts[2], raw=False)
            return topic, obj

        else:
            raise ValueError(f"Unknown encoding: {parts[1]}")
