import signal
import sys
import time
import math
import spidev
import RPi.GPIO as GPIO
from rpi_ws281x import Color, PixelStrip, ws

# rsync puzzled.py pi@testpi


# LED strip configuration:
LED_COUNT_POINTS = 10         # Number of LED pixels.
# 11 * 23 = 253
# 7 * 17 = 119
LED_COUNT_STRIP = 253         # Number of LED pixels.
LED_PIN = 21           # GPIO pin connected to the pixels (must support PWM!).
LED_FREQ_HZ = 800000   # LED signal frequency in hertz (usually 800khz)
LED_DMA = 10           # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 10   # Set to 0 for darkest and 255 for brightest
LED_INVERT = False     # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL = 0

LED_COUNT_TOTAL = LED_COUNT_POINTS + LED_COUNT_STRIP

COLORS = [
   Color(255, 0, 0),
   Color(0, 255, 0),
   Color(0, 0, 255),
   Color(0, 0, 0, 255),
   Color(255, 255, 255),
]

def wheel(pos):
    """Generate rainbow colors across 0-255 positions."""
    if pos < 85:
        return Color(pos * 3, 255 - pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return Color(255 - pos * 3, 0, pos * 3)
    else:
        pos -= 170
        return Color(0, pos * 3, 255 - pos * 3)

class Screen:
    def __init__(self):
        self.curPosPoints = 0
        self.curPosStrip = 0

        self.playerA = 0
        self.playerB = 0

        self.curColorIndex = 0
        self.flashPoints = False
        self.flashStrip = False

        # Create NeoPixel object with appropriate configuration.
        self.strip = PixelStrip(LED_COUNT_TOTAL, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
        # Intialize the library (must be called once before other functions).
        self.strip.begin()

    def updatePoints(self):
        self.strip.setPixelColor(self.curPosPoints, COLORS[self.curColorIndex])
        self.curPosPoints = self.curPosPoints + 1

        if self.curPosPoints == LED_COUNT_POINTS:
            self.curPosPoints = 0
            self.curColorIndex = (self.curColorIndex + 1) % len(COLORS)

    def updateStrip(self):
        for i in range(LED_COUNT_STRIP):
            self.strip.setPixelColor(LED_COUNT_POINTS + i, wheel(i & 255))
            # self.strip.setPixelColor(LED_COUNT_POINTS + i, Color(255, 0, 0))
        self.strip.setPixelColor(LED_COUNT_POINTS + self.playerA, Color(255, 0, 0))
        self.strip.setPixelColor(LED_COUNT_POINTS + self.playerB, Color(0, 255, 0))

    def flash(self, start, end):
        for i in range(start, end):
            self.strip.setPixelColor(i, Color(255, 255, 255))

    def update(self):
        if self.flashPoints:
            self.flash(0, LED_COUNT_POINTS)
            self.flashPoints = False
        else:
            self.updatePoints()

        if self.flashStrip:
            self.flash(LED_COUNT_POINTS, LED_COUNT_STRIP)
            self.flashStrip = False
        else:
            self.updateStrip()

        self.strip.show()


class Inputs:
    def __init__(self, screen):
        self.screen = screen
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(15, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.add_event_detect(15, GPIO.RISING, callback=self.buttonPressed)
        GPIO.add_event_detect(16, GPIO.RISING, callback=self.buttonPressed)
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 1000000 # 1MHz
        self.spi.bits_per_word = 8
        self.spi.mode = 3

    def bitstring(self, n):
        s = bin(n)[2:]
        return '0'*(8-len(s)) + s

    def buttonPressed(self, channel):
        if channel == 15:
            print("Button A pressed")
            self.screen.flashPoints = True

        if channel == 16:
            print("Button B pressed")
            self.screen.flashStrip = True

    def close(self):
        self.spi.close()
        GPIO.cleanup()

    def read(self, channel=0):
        cmd = [0b00000110, channel << 6, 0]
        replyBytes = self.spi.xfer2(cmd)
        return ((replyBytes[1] & 15) << 8) + replyBytes[2]

    def update(self):
        playerA = self.read(0)
        posA = math.floor(5 + (playerA / 4096.0) * 25)

        playerB = self.read(1)
        posB = math.floor(30 + (playerB / 4096.0) * 25)

        print(f"Position A: {playerA:.0f} - {posA}")
        print(f"Position B: {playerB:.0f} - {posB}")
        self.screen.playerA = posA
        self.screen.playerB = posB


screen = Screen()
inputs = Inputs(screen)

def signal_handler(sig, frame):
    print('You pressed Ctrl+C!')
    inputs.close()
    sys.exit(0)


# Main program logic follows:
if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    print('Press Ctrl-C to quit.')

    while True:
        inputs.update()
        screen.update()
        time.sleep(1. / 100)
