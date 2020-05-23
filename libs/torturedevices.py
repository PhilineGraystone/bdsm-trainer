class torturedevices():
    devices = []
    functions = []

    def add_device( self, name, ip, protocol ):
        device = { 'name' : name, 'ip': ip, 'protocol': protocol }
        self.devices.append( device )
    
    def add_functions( self, name, function, pic, call, args ):
        function = { 'device': name, 'func': function, 'image': pic, 'call': call, 'args': args }
        self.functions.append( function )
    
    def device_online( self, name ):
        for device in self.devices:
            if device['name'] == name:
                return True
        return False
    
    def get_device( self, name ):
        for device in self.devices:
            if device['name'] == name:
                return device

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
        return len(self.devices)