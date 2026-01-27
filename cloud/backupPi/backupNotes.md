alright so what are the things that I'd like to backup



the core stuff from 2025
- bulk data
- working data

the data exports folder
the vids to fix folder
archive of some of the older data folders

the new system minio backups
the data bucket - append only
the database state - weekly snapshots


general backup stuff
-old computers



alright so for the backup stuff it looks like it is basically rsync functionallity we're looking for
we can do object level encryption on all of the items later

for the folders in a directory situation I think we can use 

mc mirror Documents/workingData/ minio-vm/workingdata
to get the rsync like copy going (although I do still have questions about buckets vs file system)
(when it comes to the remote path on the mc mirror command)


there is still the question of a command that I could run on one of my VM's that is running minio


alright so on my current minio deployments it looks like my data drive is on mnt/data/
and then within that it looks like the bucket is also called data/ and all the things are just stored
normally

in mnt/data/ there is also some minio metadata


