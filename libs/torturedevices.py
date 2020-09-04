class torturedevices():
    devices = []
    functions = []

    def add_device( self, name, ip, protocol, online ):
        device = { 'name' : name, 'ip': ip, 'protocol': protocol, 'online': online }
        self.devices.append( device )
    
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
        i = 0
        for device in self.devices:
            if device['online'] == True:
                i = i + 1
        return i

