from painplay import painplay
from petplay import petplay

class slave:
    slave_id        = 0;
    slave_name      = ""
    slave_rfid      = ""
    slave_devices   = []
    slave_program   = ""
    slave_mode      = ""

    mqtt            = None
    devices         = None

    def __init__(self, mqtt, devices, slave_id, slave_name, rfid, program, mode):
        self.mqtt	        = mqtt
        self.devices        = devices

        self.slave_id       = slave_id
        self.slave_name 	= slave_name
        self.slave_rfid     = rfid
        self.slave_mode     = mode

        if program == "Painplay":
            self.slave_program  = painplay( self )
        if program == "Petplay":
            self.slave_program  = petplay( self )
        if program == "Condition":
            pass
        if program == "Blowjob":
            pass

    def add_device(self, device):
        self.slave_devices.append( device )
        self.mqtt.publish("punisher/devices/"+device+"/settings", "{\"slave_id\": "+str(self.slave_id)+", \"slave_name\": \""+self.slave_name+"\"} ");

    def disconnect(self):
        for device in self.slave_devices:
            self.mqtt.publish("punisher/devices/"+device+"/settings", "{\"slave_id\": 0, \"slave_name\": \""+self.slave_name+"\"} ");

    def execute(self):
        self.slave_program.execute();

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

