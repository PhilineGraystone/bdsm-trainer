from slave import slave

class slaves():
    slaves  = {}
    devices = []

    def add_slave( self, mqtt, devices, slave_id, rfid, name, program, modes ):
        if not rfid in self.slaves.keys():
            self.slaves[ rfid ] = slave( mqtt, devices, slave_id, name, rfid, program, modes )

    def slave_online( self, rfid ):
        if rfid in self.slaves.keys():
            return True
        else:
            return False

    def remove_slave( self, rfid ):
        self.slaves[ rfid ].disconnect()
        self.slaves.pop( rfid, None )

    def count_slaves( self ):
        return len( self.slaves )

    def add_device( self, rfid, device ):
        self.slaves[ rfid ].add_device( device )

    def execute_program(self):
        for slave in self.slaves.keys():
            self.slaves[ slave ].execute()




    def torture_possible(self, rfid):
        for device in self.devices:
            if device['rfid'] == rfid:
                return True
            else:
                return False

    def get_modes( self, rfid ):
        for slave in self.persons:
            if slave['rfid'] == rfid:
                return slave['modes']

    def get_id( self, rfid ):
        for slave in self.persons:
            if slave['rfid'] == rfid:
                return slave['id']

    def which( self, dev ):
        for device in self.devices:
            if device['device'] == dev:
                return device['rfid']
        return False


    def get_device( self, rfid ):
        dev = []
        for device in self.devices:
            if device['rfid'] == rfid:
                dev.append( device )
        return dev
        
    def all_slaves( self ):
        return self.persons

