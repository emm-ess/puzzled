import atexit
import curses
from typing import Union

import numpy as np

from .font import GLYPHS

try:
    import rpi_ws281x as ws
    led_usage_possible = True
except ImportError:
    led_usage_possible = False

from .const import NUM_PIXELS, NUM_PIXELS_POINTS, WIDTH, HEIGHT
from .helper import init_curses, init_draw_areas, find_closest_color_index, rgb_to_grb


# GPIO pin connected to the pixels (must support PWM!).
LED_PIN = 21
# LED signal frequency in hertz (usually 800khz)
LED_FREQ_HZ = 800000
# DMA channel to use for generating signal (try 10)
LED_DMA = 10
# True to invert the signal (when using NPN transistor level shift)
LED_INVERT = False
LED_CHANNEL = 0

TOTAL_AMOUNT_LEDS = NUM_PIXELS + NUM_PIXELS_POINTS


# LED_STRIP = ws.WS2811_STRIP_RGB
# LED_STRIP = ws.WS2811_STRIP_GBR
# LED_STRIP = ws.SK6812_STRIP_RGBW
# LED_STRIP = ws.SK6812W_STRIP

# code is a kind of copy pasta from
# https://github.com/rpi-ws281x/rpi-ws281x-python/blob/master/library/rpi_ws281x/rpi_ws281x.py

class Screen:
    def __init__(self, use_leds=led_usage_possible, use_terminal=False):
        self._leds = None
        self.use_leds = use_leds and led_usage_possible
        self.use_terminal = use_terminal or not use_leds
        self.size = TOTAL_AMOUNT_LEDS
        self.game_area_pixel = np.full((HEIGHT, WIDTH), 0, np.int32)
        self.cur_text_mask: None | np.ndarray[bool] = None

        if self.use_leds:
            self._init_leds()
            self._begin()

        if self.use_terminal:
            self._init_terminal()

        # Substitute for __del__, traps an exit condition and cleans up properly
        atexit.register(self._cleanup)

    def __getitem__(self, pos):
        """Return the 24-bit RGB color value at the provided position or slice
        of positions.
        """
        # Handle if a slice of positions are passed in by grabbing all the values
        # and returning them in a list.
        if isinstance(pos, slice):
            return [ws.ws2811_led_get(self._channel, n) for n in range(*pos.indices(self.size))]
        # Else assume the passed in value is a number to the position.
        else:
            return ws.ws2811_led_get(self._channel, pos)

    def __setitem__(self, pos, value):
        """Set the 24-bit RGB color value at the provided position or slice of
        positions.
        """
        # Handle if a slice of positions are passed in by setting the appropriate
        # LED data values to the provided value.
        if isinstance(pos, slice):
            for n in range(*pos.indices(self.size)):
                ws.ws2811_led_set(self._channel, n, value)
        # Else assume the passed in value is a number to the position.
        else:
            return ws.ws2811_led_set(self._channel, pos, value)

    def __len__(self):
        return ws.ws2811_channel_t_count_get(self._channel)

    def _init_leds(self):
        # Create ws2811_t structure and fill in parameters.
        self._leds = ws.new_ws2811_t()
        self._reset_leds()

        # Initialize the channel in use
        self._channel = ws.ws2811_channel_get(self._leds, LED_CHANNEL)

        ws.ws2811_channel_t_count_set(self._channel, TOTAL_AMOUNT_LEDS)
        ws.ws2811_channel_t_gpionum_set(self._channel, LED_PIN)
        ws.ws2811_channel_t_invert_set(self._channel, 0)
        # start with low value for brightness (until hooked up to input)
        ws.ws2811_channel_t_brightness_set(self._channel, 10)
        ws.ws2811_channel_t_strip_type_set(self._channel, ws.WS2811_STRIP_GRB)

        # Initialize the controller
        ws.ws2811_t_freq_set(self._leds, LED_FREQ_HZ)
        ws.ws2811_t_dmanum_set(self._leds, LED_DMA)

    def _reset_leds(self):
        # Initialize the channels to zero
        for channel_number in range(2):
            channel = ws.ws2811_channel_get(self._leds, channel_number)
            ws.ws2811_channel_t_count_set(channel, 0)
            ws.ws2811_channel_t_gpionum_set(channel, 0)
            ws.ws2811_channel_t_invert_set(channel, 0)
            ws.ws2811_channel_t_brightness_set(channel, 0)

    def _init_terminal(self):
        self.screen = init_curses()
        game_area, points_a_area, points_b_area = init_draw_areas()
        self.game_area = game_area
        self.points_a_area = points_a_area
        self.points_b_area = points_b_area

    def _cleanup(self):
        # Clean up memory used by the library when not needed anymore.
        if self._leds is not None:
            ws.ws2811_fini(self._leds)
            ws.delete_ws2811_t(self._leds)
            self._leds = None
            self._channel = None

    def _begin(self):
        """Initialize library, must be called once before other functions are
        called.
        """
        resp = ws.ws2811_init(self._leds)
        if resp != 0:
            str_resp = ws.ws2811_get_return_t_str(resp)
            raise RuntimeError('ws2811_init failed with code {0} ({1})'.format(resp, str_resp))

    def render(self):
        game_area = self._render_game_area()
        if self.use_leds:
            self._render_leds(game_area)
        if self.use_terminal:
            self._render_terminal(game_area)

    def _render_game_area(self):
        if self.cur_text_mask is None:
            return self.game_area_pixel
        text_width = self.cur_text_mask.shape[1]
        width = min(WIDTH, text_width)
        frame_mask = self.cur_text_mask[:,:width]
        result = np.array(self.game_area_pixel, copy=True)
        np.putmask(result, frame_mask, 0xffffff)
        return result

    def _render_leds(self, game_area) -> None:
        it = np.nditer(game_area, flags=['c_index'])
        for color in it:
            self[it.index + NUM_PIXELS_POINTS] = int(color)
        """Update the display with the data from the LED buffer."""
        resp = ws.ws2811_render(self._leds)
        if resp != 0:
            str_resp = ws.ws2811_get_return_t_str(resp)
            raise RuntimeError('ws2811_render failed with code {0} ({1})'.format(resp, str_resp))

    def _render_terminal(self, game_area) -> None:
        self.screen.clear()
        it = np.nditer(game_area, flags=['multi_index'])
        for color in it:
            color_index = find_closest_color_index(color)
            y, x = it.multi_index
            self.game_area.addch(y + 1, x * 2 + 2, curses.ACS_BLOCK, curses.color_pair(color_index))
        self.game_area.refresh()
        self.points_a_area.refresh()
        self.points_b_area.refresh()

    def get_brightness(self):
        return ws.ws2811_channel_t_brightness_get(self._channel)

    def set_brightness(self, brightness):
        """Scale each LED in the buffer by the provided brightness.  A brightness
        of 0 is the darkest and 255 is the brightest.
        """
        ws.ws2811_channel_t_brightness_set(self._channel, brightness)

    def set_game_area_pixel(self, x: int, y: int, color: int):
        self.game_area_pixel[y][x] = color

    def set_point_area_pixel(self, set_b_area: bool, pos: int, color: int):
        if self.use_leds:
            pos_led = pos
            if set_b_area:
                pos_led += 5
            self[pos_led] = rgb_to_grb(color)
        if self.use_terminal:
            color_index = find_closest_color_index(color)
            point_area = self.points_b_area if set_b_area else self.points_a_area
            point_area.addch(pos + 1, 2, curses.ACS_BLOCK, curses.color_pair(color_index))

    def fill_game_area(self, color: int):
        self.game_area_pixel.fill(color)

    def fill_point_area(self, set_b_area: bool, color: int):
        if self.use_leds:
            color_points_leds = rgb_to_grb(color)
            positions = range(5, 10) if set_b_area else range(0, 5)
            for pos in positions:
                self[pos] = color_points_leds
        if self.use_terminal:
            color_index = find_closest_color_index(color)
            point_area = self.points_b_area if set_b_area else self.points_a_area
            for pos in range(1, 6):
                point_area.addch(pos, 2, curses.ACS_BLOCK, curses.color_pair(color_index))

    def set_text(self, text: Union[str, None]):
        if text is None:
            self.cur_text_mask = None
        glyphs = np.copy(GLYPHS[text[0]])
        kerning_space = np.full((7, 1), False)
        for char in text[1:]:
            glyphs = np.concatenate((glyphs, kerning_space, GLYPHS[char]), axis=1)
        # TODO: for now we add two rows empty rows to have the same height as the play area
        line = np.full((2, glyphs.shape[1]), False)
        self.cur_text_mask = np.concatenate((line, glyphs, line), axis=0)
