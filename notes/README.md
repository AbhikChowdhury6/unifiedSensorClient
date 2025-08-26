oooo I am hyped to look at the multiprocessing managers for sharing a proper system state across processes!

what would be in the state?
basically the air qual pi object


going to start moving in code from vidcap and air qual
I would like to order my imports to make them more readable

first basic functions
sys and os and logging

and then they'll need common tools
datetime
torch
numpy
pandas

then they'll need special things
picamera2
yolo
bme280



there'll be special things for the device controllers
the state and config object
- device instance name
- responsible party name
- default logging level
- device class name
  - interface (i2c, spi, audio, video)
  - manufacturer
  - device name
  - device python module name
  - sensor
    - name of sensor stream
      - capture hz
      - rounding bits
      - col names


the device class
- a read function
  - takes in a bus in necessary
  - takes in the rounding bits
  - takes in a buffer to put the read data
  - reads and rounds and puts in the buffer with the time and datatype

- a stream function
  - takes in a buffer
  - takes in a datatype
  - has a defined type of connection that they maintain
  - has a defined way of formatting the data to send
    - jpeg
    - UTF-8
  - has a way of sending it (endpoint, socket, post)

- a persist function
  - takes in a buffer
  - takes in a persist mode (always flush)
    - 1hz
    - instant
  - has a defined way of formatting and writing the data
    - jpeg
    - mp4 h264
    - csv
    - binary



alright we're so back
so a reminder all workers will have a source

so I think that I'm making it overly generic
let's make things harder to misuse

for the intemittent frame readers High Water Mark to 1

more fundamental data types
- sensor
  - has a buss that it make sure spins up
  - has a class that describes
  - 

how about clinets are configured around sensors as first class
- sensor (implements read, and publishes, optionally uses shm for large data)
- csv writer (reads from publish and writes, publishes completed files)
- image writer (subscribes, and writes jpegs every 4s)
- h264 writer (subscribes, and writes via an ffmpeg command) (to fs shm)
- detector (subscribes, detects, publishes)
- mover(subscribes, moves files conditionally)(moves from fs shm to fs)
- deleter(subscribes, deletes files conditionally)(deletes from fs shm)

#network stuff
- json sender(subscribes and sends on an outbound socket)
- file uploader(subscribes to descriptors, posts files publishes success)

- cron job to check for cached files to send. 

(we can handle control and state later)
(we can also manually manage busses for now)



























