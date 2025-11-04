Alright so building the new sensor client
something that would be good to start with would be managing the state object
- let's start with it being local and then we can sync it later
- we'll be using the multiprocessing manager for that
- we'll be storing it in /home/pi/Documents/sensorInfo1.json and sensorInfo2.json for write rollback safety

example sensorInfo.json:
what needs to be fed?
    - platform info
    - buss info
        - camera
        - audio
        - i2c
    - devices on the buss


what are the outputs of the person detection?
what are the ipc strategies I'll be using for t

Write locations
- ram disk
  - bulk files
  - csvs
- persistent disk
  - bulk files
  - csvs
- multiprocessing manager
- multiprocessing named shared memory object



could we have a similar naming scheme for each of the locations
as well as a remote access locations?

ahhh I remember, I would use blocking requests on queues to manage pulls in a
data flow. and use a proper pub sub architecture for signaling


Alright so for each node
- we set up any libraries or models we need
- we set up the inputs (subscriptions or captures)
- we loop through either polling 
