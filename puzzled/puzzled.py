import signal
import sys
import time

from puzzled_io.screen import Screen
from puzzled_io.const import WIDTH, HEIGHT


def signal_handler(sig, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)


def wheel(pos) -> int:
    """Generate rainbow colors across 0-255 positions."""
    if pos < 85:
        return (pos * 3 << 16) + (255 - pos * 3 << 8)
    elif pos < 170:
        pos -= 85
        return (255 - pos * 3 << 16) + (pos * 3)
    else:
        pos -= 170
        return (pos * 3 << 8) + (255 - pos * 3)


offset = 0
def do_wheel(screen):
    global offset

    for i in range(5):
        color = wheel((offset + i * 25) & 0xFF)
        screen.set_point_area_pixel(False, i, color)

    for i in range(5):
        color = wheel((offset + i * 50) & 0xFF)
        screen.set_point_area_pixel(True, i, color)

    i = 0
    for y in range(HEIGHT):
        for x in range(WIDTH):
            color = wheel((offset + i) & 0xFF)
            screen.set_game_area_pixel(x, y, color)
            i += 1

    offset += 1

def do_fill(screen, color):
    screen.fill_point_area(False, color)
    screen.fill_point_area(True, color)
    screen.fill_game_area(color)


def main():
    signal.signal(signal.SIGINT, signal_handler)

    screen = Screen(True, True)

    while True:
        do_wheel(screen)
        screen.render()
        time.sleep(1. / 30)
        # do_fill(screen, 0xff0000)
        # print(screen[0], screen[4], screen[5], screen[9], screen[10])
        # screen.render()
        # time.sleep(5)
        # do_fill(screen, 0x00ff00)
        # screen.render()
        # time.sleep(5)
        # do_fill(screen, 0x0000ff)
        # screen.render()
        # time.sleep(5)


if __name__ == '__main__':
    main()
