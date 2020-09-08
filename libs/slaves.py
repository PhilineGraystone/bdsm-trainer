class slaves():
    persons = []
    devices = []

    def add_slave( self, slave_id, rfid, name, collar, program, modes ):
        slave = { 'id': slave_id, 'rfid': rfid, 'name': name, 'collar': collar, 'program': program, 'modes': modes }
        self.persons.append( slave )
    
    def slave_online( self, rfid ):
        for slave in self.persons:
            if slave['rfid'] == rfid:
                return True
        return False

    def remove_slave( self, rfid ):
        self.persons = [i for i in self.persons if not (i['rfid'] == rfid)]
        self.devices = [i for i in self.devices if not (i['rfid'] == rfid)]

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


    def add_device( self, rfid, slave, device ):
        device = { 'rfid': rfid, 'slave': slave, 'device': device }
        self.devices.append( device )

    def get_device( self, rfid ):
        dev = []
        for device in self.devices:
            if device['rfid'] == rfid:
                dev.append( device )
        return dev
        
    def all_slaves( self ):
        return self.persons

    def count_slaves( self ):
        return len( self.persons )
