'''Adapted from the Adafruit_CircuitPython_ESP32SPI
library example esp32spi_simpletest.py:
https://github.com/adafruit/Adafruit_CircuitPython_ESP32SPI/
blob/master/examples/esp32spi_simpletest.py '''

import board
import busio
import digitalio
import adafruit_requests as requests
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
from adafruit_esp32spi import adafruit_esp32spi
import time
import threading as th

#  ESP32 pins
esp32_cs = digitalio.DigitalInOut(board.CS1)
esp32_ready = digitalio.DigitalInOut(board.ESP_BUSY)
esp32_reset = digitalio.DigitalInOut(board.ESP_RESET)

# LED pins
ledr = digitalio.DigitalInOut(board.A4)
ledg = digitalio.DigitalInOut(board.D3)
ledr.direction = digitalio.Direction.OUTPUT
ledg.direction = digitalio.Direction.OUTPUT
BLINK_TIME = 1.0

# Button pins
button = digitalio.DigitalInOut(board.A5)
button.direction = digitalio.Direction.INPUT
button.pull = digitalio.Pull.UP
req_lock = th.Lock()

with open("config.txt", "r") as f:
    _id = f.read()

with open("./secret", "r") as f:
    # file that contains lines of the form ssid:psk
    known = {line.split(":")[0]:line.split(":")[1][:-1] for line in f.readlines()}

#  uses the secondary SPI connected through the ESP32
spi = busio.SPI(board.SCK1, board.MOSI1, board.MISO1)

esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

requests.set_socket(socket, esp)

def connect_psk(ssid):
    esp.connect_AP(ssid, known[ssid])    

def connect():
    while not esp.is_connected:
        try:
            for network in esp.scan_networks(): 
                ssid = network["ssid"].decode("utf-8")
                print(ssid)
                if ssid in known.keys():
                    connect_psk(ssid)
        except RuntimeError as e:
            print("bad at connecting, smh", e)
            continue
        time.sleep(2)   # retry every 2 seconds
    print("Connected to", str(esp.ssid, "utf-8"), "\tRSSI:", esp.rssi)
    print("My IP address is", esp.pretty_ip(esp.ip_address))


def signal_correct():
    ledg.value = True
    time.sleep(BLINK_TIME)
    ledg.value = False

def signal_fail():
    ledr.value = True
    time.sleep(BLINK_TIME)
    ledr.value = False


esp._debug = 1



def button_clicked():
    global _id
    while True:
        try:
            time.sleep(0.5)
            if reqs_num != 0:
                r = requests.get("http://192.168.43.128:2222/", headers={"id": _id, "time_finished": time.time()})
                msg = r.text
                if msg == "good job":
                    with req_lock:
                        reqs_num -= 1
                    _id = next(example_ids)
                    signal_correct()
                else:
                    signal_fail()
        except Exception as e:
            print("the server messed up", e)

last_value = False
reqs_num = 0
example_ids = [50]*10 + [200]*200
while True:
    time.sleep(0.1)
    if button.value != last_value:
        if not button.value: # pressed down
            with req_lock:
                reqs_num += 1
        last_value = button.value

    if not esp.status == adafruit_esp32spi.WL_CONNECTED:
        connect()

