from slaveprogram import slaveprogram

class slave:
    slave_id                = 0;
    slave_name              = ""
    slave_rfid              = ""
    slave_devices           = []
    slave_offline_devices   = []
    slave_program           = ""
    slave_mode              = ""

    mqtt            = None
    devices         = None

    def __init__(self, mqtt, devices, slave_id, slave_name, rfid, program, mode):
        self.mqtt	        = mqtt
        self.devices        = devices

        self.slave_id       = slave_id
        self.slave_name 	= slave_name
        self.slave_rfid     = rfid
        self.slave_mode     = mode
        self.slave_program  = slaveprogram( self, program )


    def add_device(self, device):
        self.slave_devices.append( device )
        self.mqtt.publish("punisher/devices/"+device+"/settings", "{\"slave_id\": "+str(self.slave_id)+", \"slave_name\": \""+self.slave_name+"\"} ");

    def add_offline_device(self, device):
        self.slave_offline_devices.append( device )

    def disconnect(self):
        for device in self.slave_devices:
            self.mqtt.publish("punisher/devices/"+device+"/settings", "{\"slave_id\": 0, \"slave_name\": \""+self.slave_name+"\"} ");

    def get_offline_device(self, off_device ):
        for device in self.slave_offline_devices:
            if device == off_device:
                return True
        return False

    def get_online_device(self, on_device ):
        for device in self.slave_devices:
            if device == on_device:
                return True
        return False


    def set_offline_device_as_online(self, off_device):
        self.remove_offline_device( off_device )
        self.add_device( off_device )

    def set_online_device_as_offline(self, on_device):
        self.remove_online_device( on_device )
        self.add_offline_device( on_device )

    def remove_offline_device(self, off_device ):
        self.slave_offline_devices.remove( off_device )

    def remove_online_device(self, on_device ):
        self.slave_devices.remove( on_device )

    def execute(self):
        self.slave_program.execute()

    def get_slave_name(self):
        return self.slave_name

    def get_slave_rfid(self):
        return self.slave_rfid

    def inital_settings(self):
        pass

    def shock(self, seconds, countdown):
        for device in self.slave_devices:
            self.devices.devices[ device ].shock( seconds, countdown )

    def vibe(self):
        pass

    def piep(self):
        pass

    def stretch(self):
        pass

    def switch(self):
        pass

    def pet(self):
        for device in self.slave_devices:
            self.devices.devices[ device ].pet()

    def wlan_fence(self):
        for device in self.slave_devices:
            self.devices.devices[ device ].wlan_fence()

    def sleep_deprivation(self):
        for device in self.slave_devices:
            self.devices.devices[ device ].sleep_deprivation()

    def remote_control(self):
        for device in self.slave_devices:
            self.devices.devices[ device ].remote_control()

    def maglock(self, minutes):
        for device in self.slave_devices:
            self.devices.devices[ device ].maglock( minutes )

    def collar_settings(self, shock, vibe, beep, duration):
        for device in self.slave_devices:
            self.devices.devices[ device ].collar_settings( shock, vibe, beep, duration )


    def blowjob(self, wait, jobcount, punishment, delay):
        for device in self.slave_devices:
            self.devices.devices[ device ].blowjob( wait, jobcount, punishment, delay )

