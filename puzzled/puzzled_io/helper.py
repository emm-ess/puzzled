import atexit
import curses
from typing import Optional

from .const import HEIGHT, WIDTH


POINTS_HEIGHT = 5
POINTS_WIDTH = 1
MAX_DISTANCE = 255 * 255 * 255
screen: Optional[curses.window] = None
colors = []


def init_curses():
    global screen
    if screen == None:
        screen = curses.initscr()
        screen.keypad(True)
        # screen.clear()
        screen.nodelay(True)
        curses.noecho()
        # curses.cbreak()
        curses.start_color()
        init_colors()
    return screen


def _cleanup():
    global screen
    if screen != None:
        # screen.clear()
        screen.keypad(False)
        # curses.nocbreak()
        curses.echo()
        curses.endwin()


atexit.register(_cleanup)


def init_colors() -> Optional[list[tuple[int, int, int]]]:
    if not curses.can_change_color():
        print('no change of color allowed')
        return

    step_size = 51
    color_index = 0
    scale = 1000 / 255

    for r in range(5):
        for g in range(5):
            for b in range(5):
                color = (r * step_size, b * step_size, g * step_size)
                colors.append(color)
                curses.init_color(color_index, int(scale * color[0]), int(scale * color[1]), int(scale * color[2]))
                curses.init_pair(len(colors), color_index, 0)
                color_index += 1


def color24_to_rgb(color_24bit: int) -> (int, int, int):
    red = (color_24bit >> 16) & 0xFF
    green = (color_24bit >> 8) & 0xFF
    blue = color_24bit & 0xFF

    return red, green, blue


def find_closest_color_index(color: int) -> int:
    r, g, b = color24_to_rgb(color)
    min_distance = MAX_DISTANCE
    min_index = 0
    for i in range(len(colors)):
        cur_r, cur_g, cur_b = colors[i]
        delta_r = r - cur_r
        delta_g = r - cur_g
        delta_b = b - cur_b
        distance = delta_r * delta_r + delta_g * delta_g + delta_b * delta_b
        if distance < min_distance:
            min_distance = distance
            min_index = i

    return min_index


def create_area(height, width, pos_y, pos_x):
    area = curses.newwin(height + 2, width * 2 + 3, pos_y, pos_x)
    area.border()
    return area


def init_draw_areas():
    game_area_pos_y = int((curses.LINES - HEIGHT - 2) / 2)
    game_area_pos_x = int((curses.COLS - WIDTH * 2 - 3) / 2)

    points_y = int((curses.LINES - POINTS_HEIGHT - 2) / 2)
    points_a_x = game_area_pos_x - POINTS_WIDTH - 3 - 5
    points_b_x = game_area_pos_x + WIDTH * 2 + 3 + 5

    game_area = create_area(HEIGHT, WIDTH, game_area_pos_y, game_area_pos_x)
    points_a_area = create_area(POINTS_HEIGHT, POINTS_WIDTH, points_y, points_a_x)
    points_b_area = create_area(POINTS_HEIGHT, POINTS_WIDTH, points_y, points_b_x)
    return game_area, points_a_area, points_b_area


def rgb_to_grb(color: int) -> int:
    red = (color >> 16) & 0xFF
    green = (color >> 8) & 0xFF
    return (green << 16) + (red << 8) + (color & 0xFF)
