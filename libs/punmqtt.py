#!/usr/bin/env python3
# coding=utf-8
import paho.mqtt.client as paho
import time

#logger = object()


class PunMQTT(paho.Client):
    tdevice = []

    def on_connect(self, mqttc, obj, flags, rc):
        if rc == 0:
            self.logger.debug('MQTT: Connection successfully established')
            self.subscribe('punisher/devices/+/response',0)
            self.subscribe('punisher/devices/+/available',0)
        elif rc == 1:
            self.logger.debug('MQTT: Connection successfully established')
            print("Wrong protocol version")
            cleanup()
            sys.exit(1)
        elif rc == 2:
            self.logger.debug('MQTT: Identification failed')
            print("Identification failed")
            cleanup()
            sys.exit(1)
        elif rc == 3:
            self.logger.debug('MQTT: Server not reachable')
            print("Server not reachable")
            cleanup()
            sys.exit(1)
        elif rc == 4:
            self.logger.debug('MQTT: User or password not correct')
            print("User or password not correct")
            cleanup()
            sys.exit(1)
        elif rc == 5:
            self.logger.debug('MQTT: Not authorized')
            print("Not authorized")
            cleanup()
            sys.exit(1)
        else:
            self.logger.debug('MQTT: Invalid return code')
            print("Invalid return code")
            cleanup()
            sys.exit(1)

    def on_message(self, mqttc, obj, msg):
#        print(msg.topic+" "+str(msg.qos)+" "+str(msg.payload))
        device = msg.topic.split('/')

        if device[3] == "available":
            if self.devices.device_online( device[2] ) == False:
                self.devices.set_online( device[2] )
                self.tdevice.append( {'device': device[1], 'timestamp': int(time.time() + 120) } )

    def on_publish(self, mqttc, obj, mid):
        self.logger.debug("MQTT - Published: "+str(mid))

    def on_subscribe(self, mqttc, obj, mid, granted_qos):
        self.logger.debug("MQTT - Subscribed: "+str(mid)+" "+str(granted_qos))

    def on_log(self, mqttc, obj, level, string):
        self.logger.debug("MQTT - FULLLOG: "+string)

    def run(self, config, logger, devices, db):
        self.logger  = logger
        self.devices = devices
        self.cursor  = db

        self.username_pw_set( config['mqtt']['username'], config['mqtt']['password'] )
        self.connect( config['mqtt']['hostname'], 1883, 60 )
        self.loop_start()
