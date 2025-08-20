"""
Shared memory circular buffer for inter-process communication using PyTorch tensors.

This module provides the `Buffer` class, which allows for storing time-stamped
data points in multiple circular buffers backed by shared memory. Designed for
use in multiprocessing scenarios where fast IPC and minimal locking are critical.

Dependencies:
- torch
- datetime
- logging
- typing
"""

import logging
from typing import Tuple, Union

from datetime import datetime, timezone
import torch

class Buffer:
    """
    A shared-memory circular buffer for time-series data.

    Maintains `num_buffs` circular buffers that store data and nanosecond-precision
    UTC timestamps. It is designed for high-throughput logging or IPC in
    multiprocessing settings.
    """
    def __init__(self,
                 hz: int,
                 seconds: int = 1,
                 num_buffs: int = 3, # an extra buffer in case a lag spike puts processing above hz
                 shape: Tuple[int, ...] = (1,),
                 dtype: torch.dtype = torch.float32,
                 debug_lvl: torch.tensor = torch.tensor([30],
                                                        dtype=torch.int32),
                 ) -> None:
        """
        Initialize a circular buffer with shared memory for IPC.

        Args:
            hz (int): Sampling frequency.
            seconds (int): Buffer length in seconds.
            num_buffs (int): Number of buffers to rotate through.
            shape (tuple[int, ...]): Shape of each data entry.
            dtype (torch.dtype): Tensor type for data.
            debug_lvl (torch.Tensor): Shared debug level scalar.
        """
        self.log = logging.getLogger("buffer")
        self.log.setLevel(int(debug_lvl[0]))

        def z_tensor(s: Tuple[int, ...] = (1,),
                     dt: torch.dtype = torch.int32,
                     val: Union[int, float] = 0,
                     ) -> torch.Tensor:
            t = torch.zeros(s, dtype=dt).share_memory_()
            if val != 0:
                t.fill(val)
            return t

        self.num_buffs = z_tensor(val=num_buffs)
        self.buff_secs = z_tensor(val=seconds)
        self.size = z_tensor(val=int(hz*seconds) + 1)

        # Used for resetting length
        self.last_bn = z_tensor()
        self.bn = z_tensor()

        # insertion points
        self.next_indexes = z_tensor((num_buffs,1))
        self.lengths = z_tensor((num_buffs,1))

        # Shared memory buffers
        buff_backbone_shape = (num_buffs, int(self.size))
        self.time_buffers = z_tensor(buff_backbone_shape, torch.int64)
        self.data_buffers = z_tensor(buff_backbone_shape + shape, dtype)

    def _buff_num(self, timestamp: datetime) -> int:
        return int(timestamp.timestamp() // self.buff_secs[0]) \
                % self.num_buffs[0]

    def __setitem__(self,
                    index: int,
                    value: Tuple[torch.Tensor, datetime]
                    ) -> None:
        """
        Set a single (data, timestamp) pair at a specific buffer index.

        Args:
            index (int): The position within the current circular buffer.
            value (Tuple[data, datetime]): Tuple of data and its timestamp.
        """
        index = index % self.size[0]  # Ensure circular indexing

        # Assume value is a tuple (data, timestamp)
        bn = self.bn[0]
        data_buf = self.data_buffers[bn]
        time_buf = self.time_buffers[bn]

        data_buf[index] = torch.as_tensor(value[0], dtype=data_buf.dtype)
        ts_ns = int(value[1].replace(tzinfo=timezone.utc).timestamp() * 1e9)
        time_buf[index] = torch.tensor(ts_ns, dtype=torch.int64)

    def append(self, value: torch.Tensor, timestamp: datetime) -> None:
        """
        Append a new data point and its timestamp to the current buffer.

        Args:
            value: The data to store (any object convertible to a torch tensor).
            timestamp (datetime): A timezone-aware datetime object.
        """
        # get the current buffer number to use
        # reset the old one if we switched
        self.last_bn[0] = self.bn[0].clone()
        self.bn[0] = self._buff_num(timestamp)
        if self.bn[0] != self.last_bn[0]:
            self.next_indexes[self.last_bn[0]][0] = 0
            self.lengths[self.bn[0]][0] = 0

        #self.log.debug(str(int(self.bn[0])))
        bn = self.bn[0]
        idx = int(self.next_indexes[bn][0])

        self[idx] = (value, timestamp)  # Use __setitem__
        self.next_indexes[bn][0] += 1
        self.lengths[bn][0] += 1
        if self.next_indexes[bn][0] >= self.size[0]:
            self.log.error("buffer %d is full", self.size[0])
            self.next_indexes[bn][0] -= 1
            self.lengths[bn][0] -= 1







