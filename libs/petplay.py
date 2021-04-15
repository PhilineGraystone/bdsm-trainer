from random import seed
from random import random
from random import randint
from datetime import datetime

class petplay():

    slave   = None
    stamp   = None

    def __init__( self, slave ):
        self.slave = slave
        self.stamp = datetime.timestamp( datetime.now() ) + 120

    def execute(self):
        if self.stamp < int( datetime.timestamp( datetime.now() ) ):
            self.slave.pet()
            self.stamp = int( datetime.timestamp( datetime.now() ) ) + 3600