import os
import numpy as np
import numpy.typing as npt


# font used:
# https://www.1001fonts.com/subway-ticker-font.html

GLYPH_HEIGHT = 7
GLYPH_ENTRY_HEIGHT = GLYPH_HEIGHT + 1
GLYPH_FILE = os.path.join(os.path.dirname(__file__), 'glyphs.txt')


def divide_chunks(unchunked_list: list, chunk_size: int) -> list[list]:
    for i in range(0, len(unchunked_list), chunk_size):
        yield unchunked_list[i:i + chunk_size]


def rehydrate_glyph(lines: list[str]) -> npt.NDArray[np.bool_]:
    glyph = []
    max_length = 0
    for line in lines:
        mapped_line = []
        for char in line:
            if char == '\n':
                continue
            mapped_line.append(char == 'X')
        glyph.append(mapped_line)
        max_length = max(max_length, len(mapped_line))
    for line in glyph:
        while len(line) < max_length:
            line.append(False)
    return np.array(glyph, dtype=bool)


def load_glyphs() -> dict[str, npt.NDArray[np.bool_]]:
    hydrated_glyphs = {}
    with open(GLYPH_FILE) as f:
        lines = f.readlines()
        if len(lines) % GLYPH_ENTRY_HEIGHT != 1:
            raise Exception('file is not dividable by 8 with remainder 1\n(first line is space-width; followed by 1 line for character + 7 lines for actual glyph for each char)')
        hydrated_glyphs[' '] = np.full((GLYPH_HEIGHT, int(lines[0])), False)
        glyph_entries = divide_chunks(lines[1:], GLYPH_ENTRY_HEIGHT)
        for entry in glyph_entries:
            glyph = rehydrate_glyph(entry[1:])
            for char in entry[0]:
                hydrated_glyphs[char] = glyph
    return hydrated_glyphs


GLYPHS = load_glyphs()
