"""Cairo scene rendering in a 480-unit circular coordinate system."""
from datetime import datetime
import math

from .touch import BUTTONS, MINIMUM, MAXIMUM, canvas

WARM = (.96, .77, .56)
TEXT = (.95, .93, .89)
MUTED = (.58, .67, .72)


def color(ctx, value):
    ctx.set_source_rgb(*value)


def line(ctx, x1, y1, x2, y2, width, rgb):
    color(ctx, rgb)
    ctx.set_line_width(width)
    ctx.move_to(x1, y1)
    ctx.line_to(x2, y2)
    ctx.stroke()


def text(ctx, value, x, y, size, rgb=TEXT, bold=False, max_width=None):
    ctx.select_font_face("DejaVu Sans", 0, 1 if bold else 0)
    value = str(value)
    ctx.set_font_size(size)
    extents = ctx.text_extents(value)
    if max_width and extents[2] > max_width:
        ctx.set_font_size(size * max_width / extents[2])
        extents = ctx.text_extents(value)
    color(ctx, rgb)
    ctx.move_to(x - extents[0] - extents[2] / 2, y)
    ctx.show_text(value)


def polar(radius, degrees):
    angle = math.radians(degrees)
    return 240 + math.cos(angle) * radius, 240 + math.sin(angle) * radius


def draw(ctx, width, height, model, config, now=None):
    """No browser, images, fonts download or HTTP server required."""
    ctx.save()
    color(ctx, (0, 0, 0))
    ctx.paint()
    left, top, scale = canvas(width, height, config["safe_inset_percent"])
    ctx.translate(left, top)
    ctx.scale(scale, scale)
    ctx.new_path()
    ctx.arc(240, 240, 240, 0, math.tau)
    ctx.clip()
    color(ctx, (.055, .085, .11))
    ctx.paint()
    color(ctx, (.10, .15, .19))
    ctx.new_path()
    ctx.arc(220, 150, 235, 0, math.tau)
    ctx.fill()
    color(ctx, (.21, .28, .33))
    ctx.set_line_width(1)
    ctx.new_path()
    ctx.arc(240, 240, 229, 0, math.tau)
    ctx.stroke()
    for i in range(57):
        degrees = 135 + i * 270 / 56
        x1, y1 = polar(202, degrees)
        x2, y2 = polar(213 if i % 4 == 0 else 208, degrees)
        line(ctx, x1, y1, x2, y2, 2 if i % 4 == 0 else 1,
             (.65, .71, .73) if i % 4 == 0 else (.36, .44, .49))
    ctx.set_line_cap(1)
    ctx.set_line_width(8)
    color(ctx, (.25, .32, .36))
    ctx.new_path()
    ctx.arc(240, 240, 185, math.radians(135), math.radians(405))
    ctx.stroke()
    fraction = (model.target - MINIMUM) / (MAXIMUM - MINIMUM)
    if fraction > 0:
        color(ctx, WARM)
        ctx.new_path()
        ctx.arc(240, 240, 185, math.radians(135), math.radians(135 + fraction * 270))
        ctx.stroke()
    x, y = polar(185, 135 + fraction * 270)
    color(ctx, (1, 1, 1) if model.action == "ring" else WARM)
    ctx.new_path()
    ctx.arc(x, y, 8, 0, math.tau)
    ctx.fill()

    text(ctx, "O R B I T", 240, 91, 17, WARM, True)
    text(ctx, config["room"].upper(), 240, 112, 12, MUTED, max_width=220)
    weather = model.weather.replace("_", " ").upper()
    text(ctx, weather or "CLIMATE", 240, 148, 14, (.73, .82, .85), max_width=210)
    text(ctx, "TARGET TEMPERATURE", 240, 180, 11, MUTED)
    text(ctx, f"{model.target:.1f}°", 240, 257, 66, TEXT)
    ambient = "—" if model.temperature is None else f"{model.temperature:.1f}"
    text(ctx, "ROOM " + ambient + " °C", 240, 282, 13, MUTED)
    for name, (cx, cy, radius) in BUTTONS.items():
        color(ctx, (.30, .38, .42) if model.action == name else (.15, .22, .27))
        ctx.new_path()
        ctx.arc(cx, cy, radius, 0, math.tau)
        ctx.fill_preserve()
        color(ctx, (.35, .43, .47))
        ctx.set_line_width(1)
        ctx.stroke()
        line(ctx, cx - 8, cy, cx + 8, cy, 3, WARM)
        if name == "increase":
            line(ctx, cx, cy - 8, cx, cy + 8, 3, WARM)
    humidity = "—" if model.humidity is None else str(round(model.humidity))
    text(ctx, humidity + "% HUMIDITY", 240, 379, 12, MUTED)
    text(ctx, "16°", 105, 382, 12, MUTED)
    text(ctx, "30°", 375, 382, 12, MUTED)
    text(ctx, (now or datetime.now()).strftime("%H:%M"), 240, 415, 23, TEXT)
    text(ctx, model.feedback, 240, 441, 10,
         (1, .59, .49) if model.error else (.58, .78, .69), max_width=208)
    ctx.restore()
