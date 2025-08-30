import msgpack
import numpy as np
import zmq


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

        if isinstance(obj, np.ndarray):
            return [
                topic_b,
                b"NDARRAY",
                obj.tobytes(),
                msgpack.packb(obj.shape),
                obj.dtype.str.encode(),
            ]
        else:
            return [topic_b, b"MSGPACK", msgpack.packb(obj)]

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
            obj = msgpack.unpackb(parts[2])
            return topic, obj

        else:
            raise ValueError(f"Unknown encoding: {parts[1]}")
