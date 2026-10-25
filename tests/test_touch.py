"""Native gesture regressions shared with Cairo's drawing coordinates."""
import math
import unittest
from orbit_app.touch import Dial, canvas, local_point


class NativeTouchTests(unittest.TestCase):
    def test_one_button_commit_and_no_second_finger_takeover(self):
        dial = Dial()
        self.assertIsNone(dial.event('begin', 1, 'touch', 316, 324))
        dial.event('begin', 2, 'touch', 164, 324)
        self.assertIsNone(dial.event('end', 2, 'touch', 164, 324))
        self.assertEqual(dial.event('end', 1, 'touch', 316, 324), 22.5)
        self.assertIsNone(dial.event('end', 1, 'touch', 316, 324))

    def test_cancel_and_release_outside_do_not_write(self):
        dial = Dial()
        for end, x, y in [('cancel', 316, 324), ('end', 240, 240)]:
            dial.event('begin', 1, 'touch', 316, 324)
            self.assertIsNone(dial.event(end, 1, 'touch', x, y))
            self.assertEqual(dial.target, 22)

    def test_ring_changes_only_on_release_and_cancel_restores(self):
        dial = Dial()
        dial.event('begin', 1, 'touch', 240, 55)
        self.assertIsNone(dial.event('update', 1, 'touch', 425, 240))
        self.assertEqual(dial.event('end', 1, 'touch', 425, 240), 27.5)
        dial.event('begin', 2, 'touch', 55, 240)
        self.assertIsNone(dial.event('cancel', 2, 'touch', 55, 240))
        self.assertEqual(dial.target, 27.5)

    def test_labels_and_bottom_gap_do_not_change_temperature(self):
        dial = Dial()
        for x, y in [(240, 240), (240, 425), (240, 10)]:
            dial.event('begin', 1, 'touch', x, y)
            self.assertIsNone(dial.event('end', 1, 'touch', x, y))
        self.assertEqual(dial.target, 22)

    def test_all_sizes_share_drawing_and_input_geometry(self):
        for size in (360, 480, 720, 800):
            for inset in (0, 3, 10):
                x, y, scale = canvas(size, size, inset)
                for px, py in [(316, 324), (164, 324), (240, 55)]:
                    local = local_point(x + px*scale, y + py*scale, size, size, inset)
                    self.assertAlmostEqual(local[0], px)
                    self.assertAlmostEqual(local[1], py)

    def test_polls_do_not_overwrite_an_active_gesture(self):
        dial = Dial()
        dial.event('begin', 1, 'touch', 240, 55)
        value = dial.target
        dial.sample({'target': 20, 'temperature': 21, 'humidity': 40, 'weather': 'sunny', 'mode': 'demo'})
        self.assertEqual(dial.target, value)
        self.assertEqual(dial.authoritative, 20)


if __name__ == '__main__':
    unittest.main()
