from torturedevice import torturedevice

class torturedevices():

    devices = []
    functions = dict()

    def add_device( self, model, device, ip, online ):
        switch = False
        for ddevice in self.devices:
            if ddevice.get_device() == device:
                switch = True

        if switch == False:
            r = torturedevice( model, device, ip, online )
            self.devices.append( r )

    def remove_device( self, device ):
        new_devices = []
        for ddevice in self.devices:
            if device != ddevice.get_device():
                new_devices.append( ddevice )
        
        self.devices = new_devices
        print( self.devices )

    def add_functions( self, name, function, pic, call, args ):
        function = { 'device': name, 'func': function, 'image': pic, 'call': call, 'args': args }
        self.functions.append( function )
    
    def device_online( self, name ):
        for device in self.devices:
            if device['name'] == name:
                if device['online'] == True:
                    return True
        return False
    
    def get_device( self, name ):
        for device in self.devices:
            if device['name'] == name:
                return device

    def set_online( self, name ):
        for device in self.devices:
            if device['name'] == name:
                self.devices.remove( { 'name' : device['name'], 'ip': device['ip'], 'protocol': device['protocol'], 'online': False } )
                self.add_device( device['name'], device['ip'], device['protocol'], True )

    def get_functions( self, name, func ):
        funcs = []
        for function in self.functions:
            if function['device'] == name:
                if function['func'] == func:
                    funcs.append( function )
        return funcs

    def support_function( self, name, func ):
        for function in self.functions:
            if function['device'] == name:
                if function['func'] == func:
                    return True
        return False

    def count_devices(self):
        i = len( self.devices )
        return i

