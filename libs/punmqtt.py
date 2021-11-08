#!/usr/bin/env python3
# coding=utf-8
import paho.mqtt.client as paho
import time

#logger = object()


class PunMQTT(paho.Client):
    tdevice = {}

    def on_connect(self, mqttc, obj, flags, rc):
        if rc == 0:
            self.logger.debug('MQTT: Connection successfully established')
            self.subscribe('punisher/devices/+/response',0)
            self.subscribe('punisher/devices/+/available',0)
            self.subscribe('$SYS/broker/uptime',0)
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

        for ddevice in self.tdevice.keys():
            if int( self.tdevice[ ddevice ][ 'timestamp' ] + 120 ) < int( time.time() ):
                self.logger.debug('MQTT: Remove a device (timeout):' + str( ddevice ) )
                self.tdevice.pop( ddevice, None )
                self.devices.remove_device( ddevice )
                self.slaves.set_online_device_to_offline( ddevice )

        if device[3] == "response":
            device = str( device[2] )
            if device in self.tdevice.keys():
                answer = msg.payload.decode("utf-8")
                if len( answer ) == 36:
                    uuids = answer.split(',')
                    self.devices.add_device( self, uuids[0], device, None, True )
                    self.tdevice[ device ] = {'timestamp': int( time.time()  + 120), 'status': 'online' }
                    self.slaves.get_slave_id_from_offline_device( device )

        if device[3] == "available":
            device = str( device[2] )
            if not device in self.tdevice.keys():
                self.logger.debug('MQTT: Announce a new device:' + str( device ) )
                self.publish('punisher/devices/'+str( device )+'/settings', '{"initial": "functions"}')
                self.tdevice[ device ] = {'timestamp': int(time.time() + 120), 'status': 'pending'}
            else:
               if self.tdevice[ device ][ 'status' ] is not 'pending':
                   self.tdevice[ device ] = {'timestamp': int(time.time() + 120), 'status': 'online'}


    def on_publish(self, mqttc, obj, mid):
        self.logger.debug("MQTT - Published: "+str(mid))

    def on_subscribe(self, mqttc, obj, mid, granted_qos):
        self.logger.debug("MQTT - Subscribed: "+str(mid)+" "+str(granted_qos))

    def on_log(self, mqttc, obj, level, string):
        self.logger.debug("MQTT - FULLLOG: "+string)

    def run(self, config, logger, devices, db, slaves):
        self.logger  = logger
        self.devices = devices
        self.cursor  = db
        self.slaves  = slaves

        self.username_pw_set( config['mqtt']['username'], config['mqtt']['password'] )
        self.connect( config['mqtt']['hostname'], 1883, 60 )
        self.loop_start()
