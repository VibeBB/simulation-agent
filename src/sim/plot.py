"""Deterministic stdlib-only plotting: PNG canvas, bitmap font, charts.

Every renderer produces identical bytes for identical input — no timestamps,
no randomness, no locale-sensitive formatting. Plots are advisory evidence
for vision review; they never change a gate verdict.

The PNG writer emits 8-bit RGB with filter 0 scanlines (IHDR/IDAT/IEND).
The embedded 5x7 bitmap font covers printable ASCII 32-126 (lowercase
letters share the uppercase shapes); anything else renders as '?'.
"""

from __future__ import annotations

import math
import re
import struct
import zlib
from collections.abc import Iterable, Sequence
from typing import Final

Color = tuple[int, int, int]

WHITE: Final[Color] = (255, 255, 255)
BLACK: Final[Color] = (33, 33, 33)
GRAY: Final[Color] = (128, 128, 128)
LIGHT_GRAY: Final[Color] = (235, 235, 235)
BAND_GREEN: Final[Color] = (226, 244, 226)
PASS_GREEN: Final[Color] = (44, 160, 44)
FAIL_RED: Final[Color] = (214, 39, 40)
UNKNOWN_GRAY: Final[Color] = (128, 128, 128)
PALETTE: Final[tuple[Color, ...]] = (
    (31, 119, 180),
    (255, 127, 14),
    (44, 160, 44),
    (214, 39, 40),
    (148, 103, 189),
    (140, 86, 75),
)
VERDICT_COLORS: Final[dict[str, Color]] = {
    "pass": PASS_GREEN,
    "fail": FAIL_RED,
    "unknown": UNKNOWN_GRAY,
}

_GLYPHS: Final[dict[str, tuple[str, ...]]] = {
    " ": ("     ", "     ", "     ", "     ", "     ", "     ", "     "),
    "!": ("  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "     ", "  #  "),
    '"': (" # # ", " # # ", " # # ", "     ", "     ", "     ", "     "),
    "#": (" # # ", " # # ", "#####", " # # ", "#####", " # # ", " # # "),
    "$": ("  #  ", " ####", "# #  ", " ### ", "  # #", "#### ", "  #  "),
    "%": ("##  #", "## # ", "   # ", "  #  ", " #   ", "# ## ", "#  ##"),
    "&": (" ##  ", "#  # ", "# #  ", " #   ", "# # #", "#  # ", " ## #"),
    "'": ("  #  ", "  #  ", " #   ", "     ", "     ", "     ", "     "),
    "(": ("   # ", "  #  ", " #   ", " #   ", " #   ", "  #  ", "   # "),
    ")": (" #   ", "  #  ", "   # ", "   # ", "   # ", "  #  ", " #   "),
    "*": ("     ", " # # ", "  #  ", "#####", "  #  ", " # # ", "     "),
    "+": ("     ", "  #  ", "  #  ", "#####", "  #  ", "  #  ", "     "),
    ",": ("     ", "     ", "     ", "     ", "  ## ", "  ## ", "  #  "),
    "-": ("     ", "     ", "     ", "#####", "     ", "     ", "     "),
    ".": ("     ", "     ", "     ", "     ", "     ", "  ## ", "  ## "),
    "/": ("    #", "    #", "   # ", "  #  ", " #   ", "#    ", "#    "),
    "0": (" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "),
    "1": ("  #  ", " ##  ", "# #  ", "  #  ", "  #  ", "  #  ", "#####"),
    "2": (" ### ", "#   #", "    #", "   # ", "  #  ", " #   ", "#####"),
    "3": ("#####", "   # ", "  #  ", "   # ", "    #", "#   #", " ### "),
    "4": ("   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "),
    "5": ("#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "),
    "6": ("  ## ", " #   ", "#    ", "#### ", "#   #", "#   #", " ### "),
    "7": ("#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "),
    "8": (" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "),
    "9": (" ### ", "#   #", "#   #", " ####", "    #", "   # ", " ##  "),
    ":": ("     ", "  ## ", "  ## ", "     ", "  ## ", "  ## ", "     "),
    ";": ("     ", "  ## ", "  ## ", "     ", "  ## ", "  ## ", "  #  "),
    "<": ("   # ", "  #  ", " #   ", "#    ", " #   ", "  #  ", "   # "),
    "=": ("     ", "     ", "#####", "     ", "#####", "     ", "     "),
    ">": (" #   ", "  #  ", "   # ", "    #", "   # ", "  #  ", " #   "),
    "?": (" ### ", "#   #", "    #", "   # ", "  #  ", "     ", "  #  "),
    "@": (" ### ", "#   #", "# ###", "# # #", "# ###", "#    ", " ### "),
    "A": (" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "B": ("#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "),
    "C": (" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "),
    "D": ("###  ", "#  # ", "#   #", "#   #", "#   #", "#  # ", "###  "),
    "E": ("#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"),
    "F": ("#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "),
    "G": (" ### ", "#   #", "#    ", "#  ##", "#   #", "#   #", " ### "),
    "H": ("#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "I": ("#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"),
    "J": ("  ###", "   # ", "   # ", "   # ", "   # ", "#  # ", " ##  "),
    "K": ("#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"),
    "L": ("#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"),
    "M": ("#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"),
    "N": ("#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"),
    "O": (" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "P": ("#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "),
    "Q": (" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"),
    "R": ("#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"),
    "S": (" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "),
    "T": ("#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "),
    "U": ("#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "V": ("#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "),
    "W": ("#   #", "#   #", "#   #", "# # #", "# # #", "## ##", "#   #"),
    "X": ("#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"),
    "Y": ("#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "),
    "Z": ("#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"),
    "[": (" ### ", " #   ", " #   ", " #   ", " #   ", " #   ", " ### "),
    "\\": ("#    ", "#    ", " #   ", "  #  ", "   # ", "    #", "    #"),
    "]": (" ### ", "   # ", "   # ", "   # ", "   # ", "   # ", " ### "),
    "^": ("  #  ", " # # ", "#   #", "     ", "     ", "     ", "     "),
    "_": ("     ", "     ", "     ", "     ", "     ", "     ", "#####"),
    "`": (" #   ", "  #  ", "   # ", "     ", "     ", "     ", "     "),
    "{": ("   ##", "  #  ", "  #  ", " #   ", "  #  ", "  #  ", "   ##"),
    "|": ("  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "),
    "}": ("##   ", "  #  ", "  #  ", "   # ", "  #  ", "  #  ", "##   "),
    "~": ("     ", "     ", " ##  ", "#  # ", "  ## ", "     ", "     "),
}


def _glyph(char: str) -> tuple[str, ...]:
    glyph = _GLYPHS.get(char) or _GLYPHS.get(char.upper()) or _GLYPHS["?"]
    return glyph


def fmt(value: float) -> str:
    """Tick-label number with three significant digits."""
    if not math.isfinite(value):
        return "?"
    return f"{value:.3g}"


class Canvas:
    """RGB pixel canvas with lines, shapes, markers and 5x7 text."""

    def __init__(self, width: int, height: int, background: Color = WHITE) -> None:
        self.width = width
        self.height = height
        self._px = bytearray(background * (width * height))

    def set_pixel(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            offset = (y * self.width + x) * 3
            self._px[offset : offset + 3] = bytes(color)

    def fill_rect(self, x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
        left, right = max(0, min(x0, x1)), min(self.width, max(x0, x1) + 1)
        top, bottom = max(0, min(y0, y1)), min(self.height, max(y0, y1) + 1)
        for y in range(top, bottom):
            for x in range(left, right):
                offset = (y * self.width + x) * 3
                self._px[offset : offset + 3] = bytes(color)

    def rect(self, x0: int, y0: int, x1: int, y1: int, color: Color, thickness: int = 1) -> None:
        self.line(x0, y0, x1, y0, color, thickness)
        self.line(x1, y0, x1, y1, color, thickness)
        self.line(x1, y1, x0, y1, color, thickness)
        self.line(x0, y1, x0, y0, color, thickness)

    def line(self, x0: int, y0: int, x1: int, y1: int, color: Color, thickness: int = 1) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        half = thickness // 2
        while True:
            self.fill_rect(x - half, y - half, x + half, y + half, color)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    def polyline(self, points: Iterable[tuple[int, int]], color: Color, thickness: int = 1) -> None:
        sequence = list(points)
        for index in range(1, len(sequence)):
            self.line(*sequence[index - 1], *sequence[index], color, thickness)

    def circle(self, cx: int, cy: int, radius: int, color: Color, filled: bool = True) -> None:
        radius = max(1, radius)
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                distance = math.hypot(x - cx, y - cy)
                if (
                    distance <= radius - 0.5
                    or (filled and distance <= radius)
                    or (not filled and distance <= radius + 0.7)
                ):
                    self.set_pixel(x, y, color)

    def text(self, x: int, y: int, value: str, color: Color = BLACK, scale: int = 1) -> int:
        cursor = x
        for char in value:
            glyph = _glyph(char)
            for row, bits in enumerate(glyph):
                for column, bit in enumerate(bits):
                    if bit == "#":
                        self.fill_rect(
                            cursor + column * scale,
                            y + row * scale,
                            cursor + column * scale + scale - 1,
                            y + row * scale + scale - 1,
                            color,
                        )
            cursor += 6 * scale
        return cursor - 6 * scale + 5 * scale

    def text_width(self, value: str, scale: int = 1) -> int:
        return len(value) * 6 * scale - scale if value else 0

    def to_png(self) -> bytes:
        def chunk(kind: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + kind
                + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
            )

        header = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        stride = self.width * 3
        raw = bytearray()
        for y in range(self.height):
            raw.append(0)
            raw += self._px[y * stride : (y + 1) * stride]
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b"")
        )


def _nice_ticks(low: float, high: float, count: int = 6) -> list[float]:
    if not (math.isfinite(low) and math.isfinite(high)) or high <= low:
        return [low]
    step = (high - low) / max(1, count - 1)
    return [low + index * step for index in range(count)]


def line_chart(
    series: Sequence[tuple[str, Sequence[float], Sequence[float]]],
    *,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    log_x: bool = False,
    hlines: Sequence[tuple[float, str]] = (),
    vspans: Sequence[tuple[float, float, str]] = (),
    width: int = 960,
    height: int = 540,
) -> bytes:
    """Line chart; AC-style plots pass log_x=True for the frequency axis."""
    canvas = Canvas(width, height)
    left, right, top, bottom = 90, width - 20, 46, height - 60
    drawn: list[tuple[str, list[float], list[float]]] = []
    xs_all: list[float] = []
    ys_all: list[float] = []
    for label, xs, ys in series:
        if len(xs) < 2 or len(xs) != len(ys):
            continue
        txs = [math.log10(max(x, 1e-300)) for x in xs] if log_x else [float(x) for x in xs]
        tys = [float(y) for y in ys]
        drawn.append((label, txs, tys))
        xs_all.extend(txs)
        ys_all.extend(tys)
    for value, _label in hlines:
        ys_all.append(value)
    for lo, hi, _label in vspans:
        xs_all.extend(
            [math.log10(max(lo, 1e-300)), math.log10(max(hi, 1e-300))] if log_x else [lo, hi]
        )
    if not xs_all or not ys_all:
        canvas.text(left, top, "no data", GRAY)
        if title:
            canvas.text(10, 10, title, BLACK, 2)
        return canvas.to_png()
    x_min, x_max = min(xs_all), max(xs_all)
    y_min, y_max = min(ys_all), max(ys_all)
    if x_max == x_min:
        x_max = x_min + 1
    if y_max == y_min:
        y_pad = abs(y_max) * 0.1 or 1
        y_min, y_max = y_min - y_pad, y_max + y_pad
    else:
        y_pad = (y_max - y_min) * 0.05
        y_min, y_max = y_min - y_pad, y_max + y_pad

    def px(value: float) -> int:
        return left + int((value - x_min) / (x_max - x_min) * (right - left))

    def py(value: float) -> int:
        return bottom - int((value - y_min) / (y_max - y_min) * (bottom - top))

    for lo, hi, label in vspans:
        a = px(math.log10(max(lo, 1e-300)) if log_x else lo)
        b = px(math.log10(max(hi, 1e-300)) if log_x else hi)
        canvas.fill_rect(min(a, b), top, max(a, b), bottom, LIGHT_GRAY)
        canvas.text(min(a, b) + 2, top + 2, label, GRAY)
    for tick in _nice_ticks(x_min, x_max):
        canvas.line(px(tick), bottom, px(tick), bottom + 4, BLACK)
        canvas.text(px(tick) - 10, bottom + 8, fmt(tick), BLACK)
        canvas.line(px(tick), top, px(tick), bottom, LIGHT_GRAY)
    for tick in _nice_ticks(y_min, y_max):
        canvas.line(left - 4, py(tick), left, py(tick), BLACK)
        canvas.text(8, py(tick) - 3, fmt(tick), BLACK)
        canvas.line(left, py(tick), right, py(tick), LIGHT_GRAY)
    canvas.line(left, top, left, bottom, BLACK)
    canvas.line(left, bottom, right, bottom, BLACK)
    for index, (label, xs, ys) in enumerate(drawn):
        color = PALETTE[index % len(PALETTE)]
        canvas.polyline([(px(x), py(y)) for x, y in zip(xs, ys, strict=True)], color, 2)
        legend_x = right - canvas.text_width(label) - 20
        legend_y = top + 8 + index * 12
        canvas.fill_rect(legend_x - 10, legend_y + 1, legend_x - 2, legend_y + 7, color)
        canvas.text(legend_x, legend_y, label, BLACK)
    for value, label in hlines:
        canvas.line(left, py(value), right, py(value), GRAY, 2)
        canvas.text(left + 4, py(value) - 10, label, GRAY)
    if xlabel:
        canvas.text((left + right) // 2 - canvas.text_width(xlabel) // 2, height - 18, xlabel)
    if ylabel:
        canvas.text(10, top - 14, ylabel)
    if title:
        canvas.text(10, 8, title, BLACK, 2)
    return canvas.to_png()


def parse_limit(text: str) -> tuple[float | None, float | None] | None:
    """Parse the limit strings the repo emits into a (low, high) window.

    Recognized forms: "≤ N[ unit][ or terminated]", "≥ N",
    "min A; max B[; measured_max C]" (bounds may be "None"), "A to B[ unit]".
    """
    number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?|None"
    match = re.match(rf"^\s*≤\s*({number})", text)
    if match:
        upper = None if match.group(1) == "None" else float(match.group(1))
        return (None, upper)
    match = re.match(rf"^\s*≥\s*({number})", text)
    if match:
        lower = None if match.group(1) == "None" else float(match.group(1))
        return (lower, None)
    match = re.match(rf"^\s*min\s+({number})\s*;\s*max\s+({number})", text)
    if match:
        low = None if match.group(1) == "None" else float(match.group(1))
        high = None if match.group(2) == "None" else float(match.group(2))
        if low is None and high is None:
            return None
        return (low, high)
    match = re.match(rf"^\s*({number})\s+to\s+({number})", text)
    if match and match.group(1) != "None" and match.group(2) != "None":
        return (float(match.group(1)), float(match.group(2)))
    return None


def margin_chart(
    rows: Sequence[tuple[str, str, float, float | None, float | None]],
    *,
    title: str = "",
    not_plotted: int = 0,
    width: int = 960,
    height: int = 540,
) -> bytes:
    """One row per check: allowed window band plus a verdict-colored marker.

    ``rows`` items are (check_id, verdict, measured, low, high); the window
    normalizes lower bound to 0 and upper bound to 1. A one-sided upper
    bound shows 0..limit, a one-sided lower bound shows limit..2*limit with
    the bound line at the left edge.
    """
    canvas = Canvas(width, height)
    left, right, top = 260, width - 120, 50
    row_height = 26
    for index, (check_id, verdict, measured, low, high) in enumerate(rows):
        y = top + index * row_height
        canvas.text(8, y + 6, check_id[:38], BLACK)
        if low is not None and high is not None:
            span_low, span_high, bound = low, high, "both"
        elif high is not None:
            span_low, span_high, bound = 0.0, high, "upper"
        elif low is not None:
            span_low, span_high, bound = low, 2 * low if low != 0 else 1.0, "lower"
        else:
            continue

        def px(value: float, lo: float = span_low, hi: float = span_high) -> int:
            return left + int((value - lo) / (hi - lo) * (right - left))

        canvas.fill_rect(left, y + 4, right, y + 18, BAND_GREEN)
        canvas.rect(left, y + 4, right, y + 18, GRAY)
        if bound == "upper":
            assert high is not None
            canvas.line(px(high), y + 2, px(high), y + 20, FAIL_RED, 2)
        elif bound == "lower":
            assert low is not None
            canvas.line(px(low), y + 2, px(low), y + 20, FAIL_RED, 2)
        else:
            assert low is not None and high is not None
            canvas.line(px(low), y + 2, px(low), y + 20, GRAY, 1)
            canvas.line(px(high), y + 2, px(high), y + 20, GRAY, 1)
        clipped = min(max(measured, span_low), span_high)
        canvas.circle(px(clipped), y + 11, 5, VERDICT_COLORS.get(verdict, UNKNOWN_GRAY))
        canvas.text(right + 8, y + 6, f"{fmt(measured)} [{verdict}]", BLACK)
    footer = top + len(rows) * row_height + 10
    if not_plotted:
        canvas.text(8, footer, f"{not_plotted} checks not plotted (no numeric limit)", GRAY)
    if title:
        canvas.text(10, 8, title, BLACK, 2)
    return canvas.to_png()


def stacked_bar_chart(
    items: Sequence[tuple[str, dict[str, int]]],
    *,
    title: str = "",
    width: int = 960,
    height: int = 540,
) -> bytes:
    """Per-analysis stacked pass/fail/unknown bars."""
    canvas = Canvas(width, height)
    left, right, top, bottom = 80, width - 30, 46, height - 60
    total_max = max(1, max(sum(counts.values()) for _name, counts in items) if items else 1)
    canvas.line(left, top, left, bottom, BLACK)
    canvas.line(left, bottom, right, bottom, BLACK)
    count = max(1, len(items))
    slot = (right - left) // count
    bar_w = min(80, max(8, slot - 20))
    for index, (name, counts) in enumerate(items):
        x0 = left + index * slot + (slot - bar_w) // 2
        y = bottom
        for verdict in ("pass", "fail", "unknown"):
            value = counts.get(verdict, 0)
            if not value:
                continue
            bar_h = round(value / total_max * (bottom - top))
            y -= bar_h
            canvas.fill_rect(x0, y, x0 + bar_w, y + bar_h - 1, VERDICT_COLORS[verdict])
            if bar_h > 10:
                canvas.text(x0 + 4, y + 3, str(value), WHITE)
        canvas.text(x0, bottom + 8, name[: max(1, slot // 7)], BLACK)
    for index, verdict in enumerate(("pass", "fail", "unknown")):
        lx = right - 210 + index * 70
        canvas.fill_rect(lx, top + 2, lx + 8, top + 8, VERDICT_COLORS[verdict])
        canvas.text(lx + 12, top, verdict, BLACK)
    for tick in _nice_ticks(0, total_max, 5):
        y = bottom - int(tick / total_max * (bottom - top))
        canvas.line(left - 4, y, left, y, BLACK)
        canvas.text(30, y - 3, str(int(tick)), BLACK)
    if title:
        canvas.text(10, 8, title, BLACK, 2)
    return canvas.to_png()


def scatter_board(
    points: Sequence[tuple[float, float, str, bool]],
    *,
    links: Sequence[tuple[float, float, float, float]] = (),
    circles: Sequence[tuple[float, float, float]] = (),
    title: str = "",
    xlabel: str = "x (mm)",
    ylabel: str = "y (mm)",
    width: int = 960,
    height: int = 540,
) -> bytes:
    """Board plan: filled markers are top side, hollow are bottom side."""
    canvas = Canvas(width, height)
    left, right, top, bottom = 80, width - 30, 46, height - 60
    xs = [x for x, _y, _label, _filled in points] + [x for x, _y, r in circles for _ in (r,)]
    xs += [x0 for x0, _y0, _x1, _y1 in links] + [x1 for _x0, _y0, x1, _y1 in links]
    xs += [x + r for x, _y, r in circles] + [x - r for x, _y, r in circles]
    ys = [y for _x, y, _label, _filled in points]
    ys += [y0 for _x0, y0, _x1, _y1 in links] + [y1 for _x0, _y0, _x1, y1 in links]
    ys += [y + r for _x, y, r in circles] + [y - r for _x, y, r in circles]
    if not xs or not ys:
        canvas.text(left, top, "no data", GRAY)
        return canvas.to_png()
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    if x_max == x_min:
        x_max += 1
    if y_max == y_min:
        y_max += 1
    pad_x = (x_max - x_min) * 0.08
    pad_y = (y_max - y_min) * 0.08
    x_min, x_max = x_min - pad_x, x_max + pad_x
    y_min, y_max = y_min - pad_y, y_max + pad_y

    def px(value: float) -> int:
        return left + int((value - x_min) / (x_max - x_min) * (right - left))

    def py(value: float) -> int:
        return bottom - int((value - y_min) / (y_max - y_min) * (bottom - top))

    for tick in _nice_ticks(x_min, x_max):
        canvas.line(px(tick), bottom, px(tick), bottom + 4, BLACK)
        canvas.text(px(tick) - 10, bottom + 8, fmt(tick), BLACK)
    for tick in _nice_ticks(y_min, y_max):
        canvas.line(left - 4, py(tick), left, py(tick), BLACK)
        canvas.text(30, py(tick) - 3, fmt(tick), BLACK)
    canvas.line(left, top, left, bottom, BLACK)
    canvas.line(left, bottom, right, bottom, BLACK)
    for x, y, radius in circles:
        r_px = max(2, int(radius / (x_max - x_min) * (right - left)))
        canvas.circle(px(x), py(y), r_px, LIGHT_GRAY, filled=False)
    for x0, y0, x1, y1 in links:
        canvas.line(px(x0), py(y0), px(x1), py(y1), FAIL_RED, 2)
    for x, y, label, filled in points:
        canvas.circle(px(x), py(y), 5, BLACK, filled=filled)
        canvas.text(px(x) + 8, py(y) - 4, label, BLACK)
    if xlabel:
        canvas.text((left + right) // 2 - 20, height - 18, xlabel)
    if ylabel:
        canvas.text(10, top - 14, ylabel)
    if title:
        canvas.text(10, 8, title, BLACK, 2)
    return canvas.to_png()
