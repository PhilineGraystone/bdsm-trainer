from torturedevice import torturedevice

class torturedevices():

    devices = {}
    functions = dict()

    def add_device( self, model, device, ip, online ):
        if not device in self.devices.keys():
            self.devices[ device ] = torturedevice( model, device, ip, online )

    def remove_device( self, device ):
        self.devices.pop( device, None )

    def get_device( self, device ):
        if not device in self.devices.keys():
            return False
        else:
            return self.devices[ device ]

    def count_devices(self):
        i = len( self.devices )
        return i

