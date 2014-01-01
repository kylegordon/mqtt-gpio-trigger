#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

__author__ = "Kyle Gordon"
__copyright__ = "Copyright (C) Kyle Gordon"

import os
import logging
import signal
import time
import socket
import sys

import mosquitto
import ConfigParser
import subprocess

# Location of WirinPi gpio command
gpio_bin_location = "/usr/local/bin/gpio"

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

# Convert the list of strings to a list of ints. Also strips any whitespace padding
PINS = map(int, PINS)

# Append a column to the list of PINS. This will be used to store state
## FIXME Should this not be in the (re)connect routine?
for item in PINS:
  PINS[PINS.index(item)] = [item,1]

client_id = "GPIO_Trigger_%d" % os.getpid()
mqttc = mosquitto.Mosquitto(client_id, clean_session=True)

LOGFORMAT = '%(asctime)-15s %(message)s'

if DEBUG:
    logging.basicConfig(filename=LOGFILE, level=logging.DEBUG, format=LOGFORMAT)
else:
    logging.basicConfig(filename=LOGFILE, level=logging.INFO, format=LOGFORMAT)

logging.info("Starting mqtt-gpio-trigger")
logging.info("INFO MODE")
logging.debug("DEBUG MODE")

## All the MQTT callbacks
def on_publish(mosq, obj, mid):
    """
    What to do when a message is published
    """
    logging.debug("MID " + str(mid) + " published.")

def on_subscribe(mosq, obj, mid, qos_list):
    """
    What to do in the event of subscribing to a topic"
    """
    logging.debug("Subscribe with mid " + str(mid) + " received.")

def on_unsubscribe(mosq, obj, mid):
    """
    What to do in the event of unsubscribing from a topic
    """
    print("Unsubscribe with mid " + str(mid) + " received.")

def on_message(mosq, obj, msg):
    print("Message received on topic " + msg.topic + " with QoS " + str(msg.qos) + " and payload " + msg.payload)

def on_connect(mosq, obj, result_code):
     """
     Handle connections (or failures) to the broker.
     This is called after the client has received a CONNACK message from the broker in response to calling connect().
     The parameter rc is an integer giving the return code:

     0: Success
     1: Refused – unacceptable protocol version
     2: Refused – identifier rejected
     3: Refused – server unavailable
     4: Refused – bad user name or password (MQTT v3.1 broker only)
     5: Refused – not authorised (MQTT v3.1 broker only)
     ## FIXME - needs fleshing out http://mosquitto.org/documentation/python/
     """
     logging.debug("on_connect RC: " + str(result_code))
     if result_code == 0:
        logging.info("Connected to broker")
        mqttc.publish("/status/" + socket.getfqdn(), "Online")
     else:
        logging.warning("Something went wrong. RC:" + str(result_code))
        cleanup()

def on_disconnect(mosq, obj, result_code):
     """
     Handle disconnections from the broker
     """
     if result_code == 0:
        logging.info("Clean disconnection")
     else:
        logging.info("Unexpected disconnection! Reconnecting in 5 seconds")
        logging.debug("Result code: %s", result_code)
        mqttc.disconnect()
        time.sleep(5)
        connect()
        main_loop()

def on_message(mosq, obj, msg):
    """
    What to do when the client recieves a message from the broker
    """
    logging.debug("Received: " + msg.payload + " received on topic " + msg.topic + " with QoS " + str(msg.qos))
    if msg.topic == "/status" and msg.payload == "status?":
        mqttc.publish("/status/" + socket.getfqdn(), "Online")

## End of MQTT callbacks

def cleanup(signum, frame):
     """
     Signal handler to ensure we disconnect cleanly 
     in the event of a SIGTERM or SIGINT.
     """
     logging.info("Disconnecting from broker")
     mqttc.publish("/status/" + socket.getfqdn(), "Offline")
     mqttc.disconnect()
     logging.info("Exiting on signal %d", signum)
     sys.exit(signum)

def connect():
    """
    Connect to the broker, define the callbacks, and subscribe
    """
    logging.info("Connecting to " + MQTT_HOST + ":" + str(MQTT_PORT))
    result = mqttc.connect(MQTT_HOST, MQTT_PORT, 60)
    logging.info("Connect complete")
    if result != 0:
        logging.info("Connection failed with error code %s. Retrying", result)
        time.sleep(10)
        connect()
    else:
        logging.info("Connected to " + MQTT_HOST + ":" + str(MQTT_PORT))

    #define the callbacks
    mqttc.on_connect = on_connect
    mqttc.on_disconnect = on_disconnect
    mqttc.on_publish = on_publish
    mqttc.on_subscribe = on_subscribe
    mqttc.on_unsubscribe = on_unsubscribe
    mqttc.on_message = on_message

    #mqttc.subscribe(MQTT_TOPIC, 2)

def export_pi_gpio():
    """
    If we're running on a Raspberry Pi, export all the pins using WiringPi
    """
    for PIN in PINS:
        index = [y[0] for y in PINS].index(PIN[0])
        logging.debug("Exporting pin %s", str(PINS[index][0]))
        result = subprocess.call("/usr/local/bin/gpio export " + str(PINS[index][0]) + " in", shell=True)
        if result != 0:
            logging.info("Failed to export pin %s", str(PINS[index][0]))
            sys.exit(result)

def set_direction():
    """
    Set the GPIO direction so that it's classed as an input
    """
    for PIN in PINS:
        index = [y[0] for y in PINS].index(PIN[0])
        logging.debug("Setting direction of pin %s", str(PINS[index][0]))
        result = subprocess.call("echo out > /sys/class/gpio/gpio" + str(PINS[index][0]) + "/direction", shell=True)
        if result != 0:
            logging.info("Failed to set the direction of pin %s", str(PINS[index][0]))
            sys.exit(result)

def main_loop():
    """
    The main loop in which we stay connected to the broker
    """
    looprc = 0
    #while mqttc.loop() == 0:
    while looprc == 0:
        logging.debug("In the loop")
        #looprc = mqttc.loop_forever()
        try:
            logging.debug("Trying MQTT loop")
            looprc = mqttc.loop()
        except:
            logging.debug("Something went wrong")
            raise SystemExit
        logging.debug("Loop RC: " + str(looprc))
        for PIN in PINS:
            index = [y[0] for y in PINS].index(PIN[0])
            logging.debug("Reading state of %s from %s", str(PINS[index][0]), str(PINS))
            path = "/sys/class/gpio/gpio" + str(PINS[index][0]) + "/value"
            filehandle = open(path, "r", 0)
            state = filehandle.readline()
            filehandle.close()
            state = int(state)
            logging.debug("Read state is %s and stored state is %s", str(state), str(PINS[index][1]))
            if state != PINS[index][1]:
                    logging.debug("Publishing state change. Pin %s changed from %s to %s", str(PINS[index][0]), str(PINS[index][1]), str(state))
                    PINS[index][1] = state
                    mqttc.publish("/raw/" + socket.getfqdn() + "/gpio/" + str(PINS[index][0]), str(state))
        time.sleep(1)
        logging.debug("End of loop")

# Use the signal module to handle signals
signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

if os.path.exists(gpio_bin_location):
    logging.info("WiringPi GPIO detected. Assumed running on a Raspberry Pi")
    export_pi_gpio()
else:
    set_direction()

#connect to broker
connect()
main_loop()
