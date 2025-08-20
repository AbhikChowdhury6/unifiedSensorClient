import time
import select
import sys
import os
import torch
import torch.multiprocessing as mp

repoPath = "/home/pi/Documents/"
sys.path.append(repoPath + "unifiedSensorClient/")


# we actually don't want to make the workers in this one, we should dynamically add them
#like we did for the i2c bus

# i can however put the smallest amount of thought into how my client classes will be layed out

#by interface type
    #by sensor type


from modelWorker import model_worker
from writerWorker import writer_worker
from piVidCap import pi_vid_cap
from circularTimeSeriesBuffer import CircularTimeSeriesBuffers

from logUtils import listener_process, worker_configurer
import logging