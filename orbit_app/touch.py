"""Circular input geometry and single-contact gestures; no GUI dependencies."""
import math

MINIMUM, MAXIMUM = 16.0, 30.0
BUTTONS = {"decrease": (164, 324, 30), "increase": (316, 324, 30)}


def canvas(width, height, inset=3):
    size = min(width, height) * (1 - 2 * inset / 100)
    return (width - size) / 2, (height - size) / 2, size / 480


def local_point(x, y, width, height, inset=3):
    left, top, scale = canvas(width, height, inset)
    return (x - left) / scale, (y - top) / scale


def angle(x, y):
    return (math.degrees(math.atan2(y - 240, x - 240)) - 135) % 360


def hit(x, y):
    for name, (cx, cy, radius) in BUTTONS.items():
        if math.hypot(x - cx, y - cy) <= radius:
            return name
    radius = math.hypot(x - 240, y - 240)
    if 145 <= radius <= 221 and angle(x, y) <= 270:
        return "ring"
    return None


def rounded(value):
    return max(MINIMUM, min(MAXIMUM, round(value * 2) / 2))


class Dial:
    def __init__(self):
        self.target = self.authoritative = 22.0
        self.contacts = set()
        self.active = None
        self.action = None
        self.before = 22.0
        self.feedback = "CONNECTING"
        self.error = False
        self.temperature = None
        self.humidity = None
        self.weather = ""
        self.mode = "demo"

    def value_at(self, x, y):
        degrees = angle(x, y)
        if degrees > 270:
            degrees = 0 if degrees > 315 else 270
        return rounded(MINIMUM + degrees / 270 * (MAXIMUM - MINIMUM))

    def event(self, kind, sequence, source, x, y):
        """Return a setpoint only once on a valid completed gesture."""
        key = (source, sequence)
        if kind == "begin":
            first = not self.contacts
            self.contacts.add(key)
            if not first:
                return None
            action = hit(x, y)
            if action is None:
                return None
            self.active, self.action, self.before = key, action, self.target
            if action == "ring":
                self.target = self.value_at(x, y)
            self.feedback, self.error = "DRAG TO SET" if action == "ring" else "RELEASE TO SET", False
        elif kind == "update" and key == self.active and self.action == "ring":
            self.target = self.value_at(x, y)
        elif kind in ("end", "cancel"):
            self.contacts.discard(key)
            if key != self.active:
                return None
            action = self.action
            self.active, self.action = None, None
            if kind == "cancel" or (action != "ring" and hit(x, y) != action):
                self.target, self.feedback = self.before, "CHANGE CANCELLED"
                return None
            if action == "ring":
                self.target = self.value_at(x, y)
            else:
                self.target = rounded(self.target + (-.5 if action == "decrease" else .5))
            if self.target == self.before:
                self.feedback = "NO CHANGE"
                return None
            self.feedback, self.error = "SAVING TARGET", False
            return self.target
        return None

    def sample(self, state, update_target=True):
        self.temperature = state["temperature"]
        self.humidity = state["humidity"]
        self.weather = str(state["weather"])
        self.mode = state["mode"]
        if update_target:
            self.authoritative = state["target"]
            if self.active is None:
                self.target = state["target"]
                self.feedback = "HOME ASSISTANT · LIVE" if self.mode == "homeassistant" else "DEMO · SIMULATED"
                self.error = False
