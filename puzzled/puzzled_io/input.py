import atexit
import curses
import math
import threading
import time
from enum import IntEnum
from typing_extensions import TypedDict

from .helper import init_curses

try:
    import spidev
    import RPi.GPIO as GPIO
    hardware_usage_possible = True
except ImportError:
    hardware_usage_possible = False

from .const import POLL_RATE, WIDTH, HEIGHT, POTENTIOMETER_MAX_VALUE

POT_A_CHANNEL = 0
POT_B_CHANNEL = 1
BRIGHTNESS_CHANNEL = 2
BUTTON_A_CHANNEL = 15
BUTTON_B_CHANNEL = 16


class ButtonCodes(IntEnum):
    pot_a_sub = ord('a')
    pot_a_add = ord('d')
    button_a = ord('s')
    pot_b_sub = curses.KEY_LEFT
    pot_b_add = curses.KEY_RIGHT
    button_b = curses.KEY_DOWN


KEYBOARD_BUTTON_KEYS = (ButtonCodes.button_a, ButtonCodes.button_b)
KEYBOARD_POSITION_KEYS = (ButtonCodes.pot_a_add, ButtonCodes.pot_a_sub, ButtonCodes.pot_b_add, ButtonCodes.pot_b_sub)


class PotentiometerState(tuple):
    def __new__(cls, quantized: int, raw: int):
        return tuple.__new__(cls, (quantized, raw))

    @property
    def quantized(self):
        return self[0]

    @property
    def raw(self):
        return self[1]


class ButtonStateType(IntEnum):
    released = 0
    pressed = 1


class ButtonState(tuple):
    def __new__(cls, state_type: ButtonStateType, since: float):
        return tuple.__new__(cls, (state_type, since))

    @property
    def type(self) -> ButtonStateType:
        return self[0]

    @property
    def since(self) -> float:
        return self[1]


class InputState(TypedDict):
    pos_a: PotentiometerState
    pos_b: PotentiometerState
    button_a: ButtonState
    button_b: ButtonState


# TODO: how to not repeat
class InputStateUpdate(TypedDict, total=False):
    pos_a: PotentiometerState
    pos_b: PotentiometerState
    button_a: ButtonState
    button_b: ButtonState


class Input:
    poll_thread = None
    input_brightness = 0
    state: InputState = {
        'pos_a': PotentiometerState(0, 0),
        'pos_b': PotentiometerState(0, 0),
        'button_a': ButtonState(ButtonStateType.released, 0),
        'button_b': ButtonState(ButtonStateType.released, 0),
    }

    def __init__(self, steps_a=WIDTH, steps_b=HEIGHT, callback=None):
        self.steps_a = steps_a
        self.steps_b = steps_b
        self.callback = callback

        if hardware_usage_possible:
            self._init_hardware()

        # Substitute for __del__, traps an exit condition and cleans up properly
        atexit.register(self._cleanup)

        self.poll_thread = Input.SpiInput(self, self.save_and_send_state_change) \
            if hardware_usage_possible \
            else Input.KeyboardInput(self, self.save_and_send_state_change)

    def _init_hardware(self):
        GPIO.setmode(GPIO.BOARD)
        self._init_hardware_button(BUTTON_A_CHANNEL)
        self._init_hardware_button(BUTTON_B_CHANNEL)

    def _init_hardware_button(self, channel):
        GPIO.setup(channel, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.add_event_detect(channel, GPIO.BOTH, callback=self.handle_button_event)

    def _cleanup(self):
        if self.poll_thread is not None:
            self.poll_thread.stop()
        if GPIO is not None:
            GPIO.cleanup()

    def start(self):
        # self.poll_thread = threading.Thread(target=target, name='InputPoll', args=(1,), daemon=True)
        self.poll_thread.start()

    def handle_button_event(self, channel: int):
        print(channel)
        print(GPIO.input(channel))
        event_type = ButtonStateType.pressed if GPIO.input(channel) else ButtonStateType.released
        event = ButtonState(event_type, time.time())
        changed: InputStateUpdate = {}
        if channel == BUTTON_A_CHANNEL:
            changed['button_a'] = event
        elif channel == BUTTON_B_CHANNEL:
            changed['button_b'] = event
        self.save_and_send_state_change(changed)

    def save_and_send_state_change(self, change: InputStateUpdate) -> None:
        self.state.update(change)
        if self.callback is not None:
            self.callback(change)

    class SpiInput(threading.Thread):
        def __init__(self, parent, callback):
            threading.Thread.__init__(self, name='SpiInputPoller', daemon=True)
            self.parent = parent
            self.input_state = parent.state
            self.callback = callback
            self.spi = spidev.SpiDev()
            self.spi.open(0, 0)
            self.spi.max_speed_hz = 1000000  # 1MHz
            self.spi.bits_per_word = 8
            self.spi.mode = 3
            self.step_width_a = POTENTIOMETER_MAX_VALUE / parent.steps_a
            self.step_width_b = POTENTIOMETER_MAX_VALUE / parent.steps_b
            self.step_width_brightness = POTENTIOMETER_MAX_VALUE / 127

        def run(self):
            while True:
                changed = self.read_player_inputs()
                self.callback(changed)
                self.parent.input_brightness = self.read(BRIGHTNESS_CHANNEL, 127).quantized
                time.sleep(1. / POLL_RATE)

        def stop(self):
            self.join()
            if self.spi is not None:
                self.spi.close()

        def read_player_inputs(self) -> InputStateUpdate:
            changed: InputStateUpdate = {}
            pos_a = self.read(POT_A_CHANNEL, self.step_width_a)
            if pos_a.quantized != self.input_state['pos_a'].quantized:
                changed['pos_a'] = pos_a
            pos_b = self.read(POT_B_CHANNEL, self.step_width_b)
            if pos_b.quantized != self.input_state['pos_b'].quantized:
                changed['pos_b'] = pos_b
            return changed

        def read(self, channel, step_width):
            cmd = [0b00000110, channel << 6, 0]
            reply_bytes = self.spi.xfer2(cmd)
            raw = ((reply_bytes[1] & 15) << 8) + reply_bytes[2]
            return PotentiometerState(math.floor(raw / step_width), raw)

    class KeyboardInput(threading.Thread):
        screen = init_curses()
        last_key = -1
        key_one_before = -1

        def __init__(self, parent, callback):
            threading.Thread.__init__(self, name='KeyboardInputPoller', daemon=True)
            self.parent = parent
            self.input_state = parent.state
            self.callback = callback

        def run(self):
            while True:
                key = self.screen.getch()
                if key == curses.ERR and key == self.last_key:
                    pass
                elif key in KEYBOARD_BUTTON_KEYS and key != self.last_key:
                    self.handle_keyboard_button(key, ButtonStateType.pressed)
                elif key == curses.ERR and self.last_key in KEYBOARD_BUTTON_KEYS:
                    self.handle_keyboard_button(self.last_key, ButtonStateType.released)
                elif key in KEYBOARD_POSITION_KEYS:
                    self.handle_keyboard_direction(key)
                self.last_key = key
                time.sleep(1. / POLL_RATE)

        def stop(self):
            self.join()

        def handle_keyboard_direction(self, key: int) -> None:
            manipulate_pos_a = key == ButtonCodes.pot_a_add or key == ButtonCodes.pot_a_sub
            adding = key == ButtonCodes.pot_a_add or key == ButtonCodes.pot_b_add

            old_value = (self.input_state['pos_a'] if manipulate_pos_a else self.input_state['pos_b']).quantized
            max_value = (self.parent.steps_a if manipulate_pos_a else self.parent.steps_b) - 1

            new_value = old_value + 1 if adding else old_value - 1
            new_value = min(max(new_value, 0), max_value)

            if new_value != old_value:
                field = 'pos_a' if manipulate_pos_a else 'pos_b'
                changed = {
                    field: PotentiometerState(new_value, new_value),
                }
                self.callback(changed)

        def handle_keyboard_button(self, key: int, event_type: ButtonStateType) -> None:
            event = ButtonState(event_type, time.time())
            changed: InputStateUpdate = {}
            if key == ButtonCodes.button_a:
                changed['button_a'] = event
            elif key == ButtonCodes.button_b:
                changed['button_b'] = event
            self.callback(changed)
