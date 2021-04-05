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

        if device[3] == "response":
            for ddevice in self.tdevice:
                if ddevice['device'] == device[2]:
                    answer = msg.payload.decode("utf-8")
                    if len( answer ) == 73:
                        uuids = answer.split(',')
                        self.devices.add_device( uuids[0], uuids[1], None, True )
                        self.tdevice.remove( {'device': ddevice['device'], 'timestamp': ddevice['timestamp'], 'status': 'pending' } )
                        self.tdevice.append( {'device': ddevice['device'], 'timestamp': int(time.time() + 120), 'status': 'online' } )

        if device[3] == "available":
            must_add = True

            for ddevice in self.tdevice:
                if int( ddevice['timestamp'] ) < int( time.time() ):
                    self.tdevice.remove( {'device': ddevice['device'], 'timestamp': ddevice['timestamp'], 'status': 'online' } )
                    self.devices.remove_device( ddevice['device'] )


            for ddevice in self.tdevice:
                if ddevice['device'] == device[2]:
                    must_add = False
                    if ddevice['status'] == "pending":
                        if int( ddevice['timestamp'] ) < int( time.time() ):
                            self.tdevice.remove( {'device': ddevice['device'], 'timestamp': ddevice['timestamp'], 'status': 'pending' } )
                            break

                    if ddevice['status'] == "online":
                        self.tdevice.remove( {'device': ddevice['device'], 'timestamp': ddevice['timestamp'], 'status': 'online' } )
                        self.tdevice.append( {'device': ddevice['device'], 'timestamp': int(time.time() + 120), 'status': 'online' } )
                        break
                print( self.tdevice )

            if must_add == True:
                self.publish('punisher/devices/'+str( device[2] )+'/settings', '{"initial": "functions"}')
                self.tdevice.append( {'device': device[2], 'timestamp': int(time.time() + 120), 'status': 'pending' } )

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
