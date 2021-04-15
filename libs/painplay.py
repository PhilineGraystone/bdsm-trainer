from random import seed
from random import random
from random import randint
from datetime import datetime

class painplay():

    slave   = None
    stamp   = None

    def __init__( self, slave ):
        self.slave = slave
        self.stamp = datetime.timestamp( datetime.now() ) + 120

    def execute(self):
        if self.stamp < int( datetime.timestamp( datetime.now() ) ):
            value   = randint( 0, 5 )
            counter = randint( 0, 30 )

            if value == 1:
                mode = randint( 1, 6 )
                if mode == 1:
                    seconds = 10
                if mode == 2:
                    seconds = 15
                if mode == 3:
                    seconds = 20
                if mode == 4:
                    seconds = 25
                if mode == 5:
                    seconds = 30
                if mode == 6:
                    seconds = 35

                self.stamp = int( datetime.timestamp( datetime.now() ) ) + seconds + counter + randint( 60, 120 )
                self.slave.shock( seconds, counter )

