# things we'll be doing



# read the all process configs

# the numbers will indicate for me if I should have them loaded or not

#generate template unit files for all of the services
#generate config files for all of the services
    #this will be in the form of a dictionary where the key is the template instance name

#generate a target unit file
    #

#




#alright I'll be using the bus location as the parameter to my template units
#or should it be the whole topic name, yeah it should be for software bus locations

#the template units in general can keep the names of the .py's their associated with
#I'll rename my files to use underscores so they can have the same name as their services


#Maybe I should have get config be a function in utils too
#it's passed in the whole topic name (which in this case will just be used to look up in
#a standard config dictionary)
#I of course also have to add main to all of my services






#alright a reminder that 
# all files will be in /etc/systemd/system/
#the unit file templates will be named the same as the process name with a .service extension
#ex. i2c_controller.service
#calling the template will look like
#i2c_controller@i2c-1.service
#then i2c-1's config will have the sensors to spawn
#the sensor will have all the context and config needed to spawn a writer process
#how about this is where we use mp shared memory objects to store the whole config
#and the name of that object is the same as the writer process parameter
#writer@i2c-1-0x77_bosch-bme680_air-pressure_kpa_int16-f7_wavpak-1_16hz.service

#so that means it's on the sensor object to create the shared memory object
#then ask the orchestrator to spawn the writer process















