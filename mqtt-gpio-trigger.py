#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

__author__ = "Kyle Gordon"
__copyright__ = "Copyright (C) Kyle Gordon"

import os
import csv
import logging
import signal
import time
import socket

import mosquitto
import ConfigParser

# Read the config file
config = ConfigParser.RawConfigParser()
config.read("/etc/mqtt-gpio-trigger/mqtt-gpio-trigger.cfg")

#Use ConfigParser to pick out the settings
DEBUG = config.getboolean("global", "debug")
LOGFILE = config.get("global", "logfile")
MQTT_HOST = config.get("global", "mqtt_host")
MQTT_PORT = config.getint("global", "mqtt_port")
MQTT_TOPIC = config.get("global", "mqtt_topic")
PINS = config.get("global", "pins").split(",")

client_id = "GPIO_Trigger_%d" % os.getpid()
mqttc = mosquitto.Mosquitto(client_id)

if DEBUG:
    logging.basicConfig(filename=LOGFILE, level=logging.DEBUG)
else:
    logging.basicConfig(filename=LOGFILE, level=logging.INFO)

logging.info("Starting mqtt-gpio-trigger")
logging.info("INFO MODE")
logging.debug("DEBUG MODE")

def cleanup(signum, frame):
     """
     Signal handler to ensure we disconnect cleanly 
     in the event of a SIGTERM or SIGINT.
     """
     logging.info("Disconnecting from broker")
     mqttc.publish("/status/" + socket.getfqdn(), "Offline")
     mqttc.disconnect()
     logging.info("Exiting on signal %d", signum)

def connect():
    """
    Connect to the broker, define the callbacks, and subscribe
    """
    mqttc.connect(MQTT_HOST, MQTT_PORT, 60, True)

    #define the callbacks
    mqttc.on_message = on_message
    mqttc.on_connect = on_connect
    mqttc.on_disconnect = on_disconnect

    mqttc.subscribe(MQTT_TOPIC, 2)

def on_connect(result_code):
     """
     Handle connections (or failures) to the broker.
     """
     ## FIXME - needs fleshing out http://mosquitto.org/documentation/python/
     if result_code == 0:
        logging.info("Connected to broker")
        mqttc.publish("/status/" + socket.getfqdn(), "Online")
     else:
        logging.warning("Something went wrong")
        cleanup()

def on_disconnect(result_code):
     """
     Handle disconnections from the broker
     """
     if result_code == 0:
        logging.info("Clean disconnection")
     else:
        logging.info("Unexpected disconnection! Reconnecting in 5 seconds")
        logging.debug("Result code: %s", result_code)
        time.sleep(5)
        connect()
        main_loop()

def on_message(msg):
    """
    What to do when the client recieves a message from the broker
    """
    logging.debug("Received: %s", msg.topic)

def main_loop():
        """
        The main loop in which we stay connected to the broker
        """
        while mqttc.loop() == 0:
                logging.debug("Looping")
		for pin in pins:
			state[pin] = call(["gpio", "-g read " + pin ])
	        	if state[pin] != oldstate[pin]:
        			mqttc.publish(MQTT_TOPIC, state[pin])
        			oldstate[pin] = state[pin]

# Use the signal module to handle signals
signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

#connect to broker
connect()

main_loop()
