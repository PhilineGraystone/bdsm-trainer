#!/usr/bin/env python3
# coding=utf-8

# Bibliotheken importieren
import sys
punisherdir = sys.path[0]
sys.path.append( punisherdir+'/libs' )

from lib_oled96 import ssd1306
from smbus import SMBus
from PIL import Image
from time import sleep
from collections import defaultdict
from random import seed
from random import random
from random import randint
from datetime import datetime
from urllib.request import urlopen
from torturedevices import torturedevices
from slaves import slaves
from rpi_rf import RFDevice
from punmqtt import PunMQTT
import logging
import configparser
#import paho.mqtt.client as paho
import RPi.GPIO as GPIO
import MFRC522
import signal
import lcddriver
import json
import random
import pymysql
import os
import time
import signal

stamp = dict()
realstamp = dict()
tordevices = torturedevices()
slaves = slaves()
rfdevice = RFDevice( 27 )
rfsend   = RFDevice( 17 )
rfdevice.enable_rx()
rfsend.enable_tx()
rfdevice.tx_repeat = 10
old_slave_count = -1
old_device_count = -1
logger = logging.getLogger( 'Punisher' )
logger.setLevel( logging.DEBUG )
log = logging.FileHandler('logs/punisher.log')
log.setLevel( logging.DEBUG )
logger.addHandler( log )
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log.setFormatter( formatter )
logger.addHandler( log )

config = configparser.ConfigParser()
config.read('config/config.ini')

i2cbus = SMBus(1)
oled = ssd1306(i2cbus)
lcd = lcddriver.lcd()
draw = oled.canvas
MIFAREReader = MFRC522.MFRC522()

def cleanup():
    lcd.lcd_clear()
    oled.cls()
    oled.display()
    GPIO.cleanup()
    db.close()
    rfdevice.cleanup()
    rfsend.cleanup()

def showLogo():
    oled.cls()
    oled.display()
    draw.bitmap((32, 0), Image.open(punisherdir+'/pics/bdsm.png'), fill=1)
    oled.display()

def showfunc( pic ):
    oled.cls()
    oled.display()
    draw.bitmap((32, 0), Image.open(punisherdir+'/pics/'+pic), fill=1)
    oled.display()

def showLCD(line1, line2):
    lcd.lcd_clear()
    lcd.lcd_display_string(line1, 1)
    lcd.lcd_display_string(line2, 2)

def listToString(s):
    str1 = ""  
    for ele in s:  
        str1 += str(ele)
    return str1  

def defaultLCD():
    global tordevices, old_slave_count, old_device_count

    if old_slave_count != slaves.count_slaves() or old_device_count != tordevices.count_devices():
        if slaves.count_slaves() == 0:
            showLCD('BDSM Trainer', str(tordevices.count_devices())+' Devices found')
        else:
            showLCD(str(slaves.count_slaves())+' Slave avail.', str(tordevices.count_devices())+' Devices found')
        old_slave_count = slaves.count_slaves()
        old_device_count = tordevices.count_devices()

def load_program( slave_id ):
    global cursor
    cursor.execute('SELECT * FROM slave_program WHERE sp_slave = "'+str( slave_id )+'" AND sp_enabled = "Y"')
    program_details = cursor.fetchone()

    cursor.execute('SELECT * FROM program_commands WHERE pc_program = "'+str( program_details[0] )+'"')
    commands = cursor.fetchall()
    return( commands )
    

def program():
    slaves.execute_program()

def rfid():
    (status,TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)
    if status == MIFAREReader.MI_OK:
        (status,uid) = MIFAREReader.MFRC522_Anticoll()
        key = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
        try:
            MIFAREReader.MFRC522_SelectTag(uid)
        except:
            log.warning('RFID has an error')
        status = MIFAREReader.MFRC522_Auth(MIFAREReader.PICC_AUTHENT1A, 8, key, uid)
        if status == MIFAREReader.MI_OK:
            data = MIFAREReader.MFRC522_Read(8)
            MIFAREReader.MFRC522_StopCrypto1()
            slaveid = listToString(data[:9])
            cursor.execute('SELECT * FROM slaves, program WHERE slave_rfid = "'+slaveid+'" AND pro_id = slave_program')
            slave = cursor.fetchone()
            if slave is None:
                logger.info( 'Slave not found - RFID '+slaveid )
                showLCD('Slave not found','')
                sleep(2)
                defaultLCD()
            else:
                if slaves.slave_online( slave[1] ):
                    logger.debug( "Slave '"+slave[2]+"'  disconnected - RFID "+slaveid )
                    slaves.remove_slave( slave[1] )
                    showLCD(slave[2], 'Slave disconnected')
                    sleep(2)
                    showLCD('Training program', 'disabled...')
                    sleep(2)
                    defaultLCD()
                else:
                    logger.debug( "Slave '"+slave[2]+"' connected - RFID "+slaveid )
                    program = load_program( slave[0] )
                    slaves.add_slave( punmqtt, tordevices, slave[0], slave[1], slave[2], program, slave[7] )
                    stamp[ slave[1] ] = datetime.timestamp( datetime.now() )
                    realstamp[ slave[1] ] = datetime.timestamp( datetime.now() )
                    cursor.execute('SELECT * FROM devtoslave, devices WHERE dts_slaveid = "'+str(slave[0])+'" AND dev_id = dts_deviceid')
                    device = cursor.fetchall()
                    for dev in device:
                        if tordevices.device_online( dev[4] ):
                            slaves.add_device( slave[1], dev[4] )
                        else:
                            slaves.add_offline_device( slave[1], dev[4] )

                    showLCD(slave[2], 'Slave connected')
                    sleep(2)
                    showLCD('Training program', slave[6]+' started...')
                    sleep(10)
                    defaultLCD()

    


try:
    db = pymysql.connect( config['database']['hostname'], config['database']['username'], config['database']['password'], config['database']['database'] )
except:
    print("Error: MySQL connection failed, program start failed")
    lcd.lcd_clear()
    oled.cls()
    oled.display()
    GPIO.cleanup()
    db.close()
    rfdevice.cleanup()
    rfsend.cleanup()
    mqtt.loop.stop()
    sys.exit(1)

cursor = db.cursor()

punmqtt = PunMQTT('Punisher')
punmqtt.run( config, logger, tordevices, cursor, slaves )

showLogo()
defaultLCD()

try:
    while True:
        rfid()
        defaultLCD();
        if slaves.count_slaves() > 0 and tordevices.count_devices() > 0:
            program()

except KeyboardInterrupt:
    cleanup()
