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
mqttdevices = dict()
tordevices = torturedevices()
slaves = slaves()
rfdevice = RFDevice( 27 )
rfsend   = RFDevice( 17 )
rfdevice.enable_rx()
rfsend.enable_tx()
rfdevice.tx_repeat = 10
timestamp = None
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
    global tordevices
    if slaves.count_slaves() == 0:
        showLCD('BDSM Trainer', str(tordevices.count_devices())+' Devices found')
    else:
        showLCD(str(slaves.count_slaves())+' Slave avail.', str(tordevices.count_devices())+' Devices found')

def shock( rfid, mode ):
    global stamp, realstamp, punmqtt

    devices = slaves.get_device( rfid )
    if realstamp[ rfid ] > 0 and realstamp[ rfid ] < int( datetime.timestamp( datetime.now()) ):
        showLogo()
        realstamp[ rfid ] = 0

    for dev in devices:
        if tordevices.support_function( dev['device'], 'tens' ):
            device = tordevices.get_device( dev['device'] )
            funcs   = tordevices.get_functions( dev['device'], 'tens' )
            for i in funcs:
                if int(datetime.timestamp( datetime.now()) ) > stamp[ rfid ]:
                    value = random.randint(0, 30)
                    counter = random.randint(0, 30)
                    if value == 1:
                        mode = randint(1,6)
                        if mode == 1:
                            seconds = 10
                        elif mode == 2:
                            seconds = 30
                        elif mode == 3:
                            seconds = 60
                        elif mode == 4:
                            seconds = 90
                        elif mode == 5:
                            seconds = 120
                        elif mode == 6:
                            seconds = 160

                        stamp[ rfid ]     = int(datetime.timestamp( datetime.now() )) + seconds + counter +random.randint(10, 120)
                        realstamp[ rfid ] = int(datetime.timestamp( datetime.now() )) + seconds + counter
                        if device['protocol'] == "MQTT":
                            punmqtt.publish('punisher/functions/shock', str(counter)+','+str(seconds) )
                        if i['image'] != "":
                            showfunc( i['image'] )

def shock_punish( rfid, seconds ):
    global stamp, realstamp
    devices = slaves.get_device( rfid )

    for dev in devices:
        if tordevices.support_function( dev['device'], 'tens' ):
            device = tordevices.get_device( dev['device'] )
            funcs   = tordevices.get_functions( dev['device'], 'tens' )
            for i in funcs:
                if device['protocol'] == "MQTT":
                    punmqtt.publish('punisher/functions/shock', str(counter)+','+str(seconds) )
                if i['image'] != "":
                    showfunc( i['image'] )

def blowjob( rfid, seconds ):
    global stamp, realstamp
    devices = slaves.get_device( rfid )
    if realstamp[ rfid ] > 0 and realstamp[ rfid ] < int( datetime.timestamp( datetime.now()) ):
        showLogo()
        realstamp[ rfid ] = 0

    for dev in devices:
        if tordevices.support_function( dev['device'], 'blowjob' ):
            device = tordevices.get_device( dev['device'] )
            funcs   = tordevices.get_functions( dev['device'], 'blowjob' )
            for i in funcs:
                if int(datetime.timestamp( datetime.now()) ) > stamp[ rfid ]:
                    seconds = int(seconds)
                    stamp[ rfid ]     = int(datetime.timestamp( datetime.now() )) + seconds + random.randint(10, 120)
                    realstamp[ rfid ] = int(datetime.timestamp( datetime.now() )) + seconds

                    if device['protocol'] == "http":
                        url = "http://"+device['ip']+"/"+i['call']+"?Seconds="+str(seconds)
                        with urlopen( url ) as conn:
                            resp = conn
                    elif device['protocol'] == "https":
                        url = "https://"+device['ip']+"/"+i['call']+"?Seconds="+str(seconds)
                        with urlopen( url ) as conn:
                            resp = conn
                    elif device['protocol'] == "433":
                        code = device['ip']+str(seconds)
                        rfsend.tx_code(int(code), 1, 350, 32)

                    if i['image'] != "":
                        showfunc( i['image'] )


def painplay( rfid ):
    global stamp, slaves
    modes = slaves.get_modes( rfid )
    modes = modes.split(',')
    for mode in modes:
        func = mode.split('|')
        if func[0] == "tens":
            shock( rfid, func[1] )

def blowjobtraining( rfid ):
    global stamp, slaves
    modes = slaves.get_modes( rfid )
    modes = modes.split(',')
    for mode in modes:
        func = mode.split('|')
        if func[0] == "blowjob":
            blowjob( rfid, func[1] )

def program():
    global stamp
    for slave in slaves.all_slaves():
        if slaves.torture_possible( slave['rfid'] ):
            if slave['program'] == "Painplay":
                painplay( slave['rfid'] )
            elif slave['program'] == "Petplay":
                print('Start Petplay')
            elif slave['program'] == "Condition":
                print('Start Condition')
            elif slave['program'] == "Blowjob":
                blowjobtraining( slave['rfid'] )
            else:
                logger.error('Training program not found')
        else:
            logger.warning('Slave has no training program')

def r433():
# Codebased = 99011110
# 99 = fixed
# 01 = device01 // 02 = device02 // 03 = device03 // 00 = this device
# 1  = punish
# 1  = tens
# 10 = seconds

    global timestamp
    if rfdevice.rx_code_timestamp != timestamp:
        timestamp = rfdevice.rx_code_timestamp
        response = str(rfdevice.rx_code)
        valid  = response[0]+response[1]
        if valid == "99":
            if len(response) != 6:
                device = "torturedevice"+response[2]+response[3]
                function = response[4]
                args = response[5]
                seconds = int(response[6]+response[7])
                slave = slaves.which( device )
                if slave != "":
                    if function == "1":
                        shock_punish( slave, seconds )

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
                    slaves.add_slave( slave[1], slave[2], slave[3], slave[6], slave[7] )
                    stamp[ slave[1] ] = datetime.timestamp( datetime.now() )
                    realstamp[ slave[1] ] = datetime.timestamp( datetime.now() )
                    cursor.execute('SELECT * FROM devtoslave, devices WHERE dts_slaveid = "'+str(slave[0])+'" AND dev_id = dts_deviceid')
                    device = cursor.fetchall()
                    for dev in device:
                        if tordevices.device_online( dev[4] ):
                            slaves.add_device( slave[1], slave[2], dev[4] )

                    showLCD(slave[2], 'Slave connected')
                    sleep(2)
                    showLCD('Training program', slave[6]+' started...')
                    sleep(2)
                    defaultLCD()

deviceavail = defaultdict(list)
i2cbus = SMBus(1)
oled = ssd1306(i2cbus)
lcd = lcddriver.lcd()
draw = oled.canvas
MIFAREReader = MFRC522.MFRC522()

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
punmqtt.run( config, logger, tordevices, cursor )

cursor.execute('SELECT * FROM devices, torfunctions WHERE tf_devid = dev_id')
devices = cursor.fetchall()

for device in devices:
    if device[3] == "433":
        code = device[2]+str("000");
        rfsend.tx_code(int(code), 1, 350, 32)
        timeout = int(datetime.timestamp( datetime.now() )) + 10
        time.sleep(1)
        while True:
            if rfdevice.rx_code_timestamp != timestamp:
                timestamp = rfdevice.rx_code_timestamp
                response = str(rfdevice.rx_code);
                if response == "99"+str(device[2][2])+str(device[2][3])+"00":
                    tordevices.add_device( device[1], device[2], device[3] )
                    tordevices.add_functions( device[1], device[6], device[7], device[8], device[9] )
                    time.sleep(2)
                    break;
            if timeout < int(datetime.timestamp( datetime.now() )):
                break;

timestamp = None
showLogo()
defaultLCD()

try:
    while True:
        rfid()
        if slaves.count_slaves() > 0 and tordevices.count_devices() > 0:
            r433()
            program()

except KeyboardInterrupt:
    cleanup()
