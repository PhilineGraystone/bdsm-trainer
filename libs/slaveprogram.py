from random import seed
from random import random
from random import randint
from datetime import datetime

class slaveprogram():

    program     = None
    slave       = None
    stamp       = None
    nextaction  = None

    def __init__( self, slave, slaveprogram ):
        self.slave      = slave
        self.program    = slaveprogram
        self.stamp      = datetime.timestamp( datetime.now() )
        self.nextaction = datetime.timestamp( datetime.now() ) + 60
        
        self.execute()

    def execute( self ):
        if int( self.nextaction ) < int( datetime.timestamp( datetime.now() ) ):
            if len( self.program ) > 0:
                active = False
                if active == False and len( self.program ) > 0 and self.program[0][2] == "SHOCK":
                    print( "Execute SHOCK" )
                    parameter = self.program[0][3].split('|')
                    self.nextaction = int( datetime.timestamp( datetime.now() ) ) + int( parameter[0] ) + int( parameter[1] ) + 10
                    self.slave.shock( parameter[0], parameter[1] )
                    active = True
                    if len( self.program ) > 0:
                        self.program = self.program[1:]

                if active == False and len( self.program ) > 0 and self.program[0][2] == "PET":
                    print( "Switch to PET Mode" )
                    self.slave.pet()
                    active = True
                    if len( self.program ) > 0:
                        self.program = self.program[1:]

                if active == False and len( self.program ) > 0 and self.program[0][2] == "WLAN_FENCE":
                    print( "Switch to WLAN Fence Mode" )
                    self.slave.wlan_fence()
                    active = True
                    if len( self.program ) > 0:
                        self.program = self.program[1:]

                if active == False and len( self.program ) > 0 and self.program[0][2] == "SLEEP_DEPRIVATION":
                    print( "Switch to SLEEP DEPRIVATION Mode" )
                    self.slave.sleep_deprivation()
                    active = True
                    if len( self.program ) > 0:
                        self.program = self.program[1:]

                if active == False and len( self.program ) > 0 and self.program[0][2] == "REMOTE_CONTROL":
                    print( "Switch to REMOTE CONTROL Mode" )
                    self.slave.remote_control()
                    active = True
                    if len( self.program ) > 0:
                        self.program = self.program[1:]

                if active == False and len( self.program ) > 0 and self.program[0][2] == "MAGLOCK":
                    print( "Execute MAGLOCK" )
                    parameter = self.program[0][3]
                    self.slave.maglock( parameter  )
                    active = True
                    if len( self.program ) > 0:
                        self.program = self.program[1:]

                if active == False and len( self.program ) > 0 and self.program[0][2] == "WAIT":
                    print( "Execute WAIT" )
                    self.nextaction = int( datetime.timestamp( datetime.now() ) ) + ( int( self.program[0][3] ) * 60 )
                    active = True
                    if len( self.program ) > 0:
                        self.program = self.program[1:]

            