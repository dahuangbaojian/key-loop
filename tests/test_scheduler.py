import unittest

from key_loop_core import KeyBinding, KeyScheduler, perform_key_press


class KeySchedulerTests(unittest.TestCase):
    def setUp(self):
        self.scheduler = KeyScheduler()

    def test_simultaneous_slots_are_dispatched_serially(self):
        bindings = (
            KeyBinding(0, 0x3B, False, 1.0),
            KeyBinding(1, 0x3C, False, 2.0),
        )

        self.assertEqual(
            self.scheduler.next_press(0.0, True, bindings), bindings[0]
        )
        self.assertEqual(
            self.scheduler.next_press(0.03, True, bindings), bindings[1]
        )
        self.assertIsNone(
            self.scheduler.next_press(0.99, True, bindings)
        )
        self.assertEqual(
            self.scheduler.next_press(1.0, True, bindings), bindings[0]
        )

    def test_restart_triggers_enabled_slot_immediately(self):
        bindings = (KeyBinding(0, 0x3B, False, 1.0),)
        self.scheduler.next_press(0.0, True, bindings)

        self.assertIsNone(self.scheduler.next_press(0.1, False, bindings))
        self.assertEqual(
            self.scheduler.next_press(0.2, True, bindings), bindings[0]
        )

    def test_key_edit_takes_effect_immediately(self):
        original = (KeyBinding(0, 0x3B, False, 1.0),)
        updated = (KeyBinding(0, 0x3C, False, 1.0),)
        self.scheduler.next_press(0.0, True, original)

        self.assertEqual(
            self.scheduler.next_press(0.1, True, updated), updated[0]
        )

    def test_duplicate_keys_are_separate_taps(self):
        bindings = (
            KeyBinding(0, 0x3B, False, 1.0),
            KeyBinding(1, 0x3B, False, 2.0),
        )

        self.assertEqual(
            self.scheduler.next_press(0.0, True, bindings), bindings[0]
        )
        self.assertEqual(
            self.scheduler.next_press(0.03, True, bindings), bindings[1]
        )

    def test_interval_edit_starts_a_fresh_interval(self):
        original = (KeyBinding(0, 0x3B, False, 1.0),)
        updated = (KeyBinding(0, 0x3B, False, 10.0),)
        self.scheduler.next_press(0.0, True, original)

        self.assertIsNone(
            self.scheduler.next_press(0.5, True, updated)
        )
        self.assertIsNone(
            self.scheduler.next_press(10.49, True, updated)
        )
        self.assertEqual(
            self.scheduler.next_press(10.5, True, updated), updated[0]
        )

    def test_wait_is_bounded_by_next_deadline(self):
        bindings = (KeyBinding(0, 0x3B, False, 1.0),)
        self.scheduler.next_press(0.0, True, bindings)

        self.assertAlmostEqual(self.scheduler.next_delay(0.0), 0.05)
        self.assertAlmostEqual(self.scheduler.next_delay(0.98), 0.02)

    def test_missed_intervals_do_not_create_a_burst(self):
        bindings = (KeyBinding(0, 0x3B, False, 0.01),)
        self.scheduler.next_press(0.0, True, bindings)

        self.assertEqual(
            self.scheduler.next_press(1.0, True, bindings), bindings[0]
        )
        self.assertIsNone(
            self.scheduler.next_press(1.005, True, bindings)
        )


class KeyPressTests(unittest.TestCase):
    def test_hold_starts_after_key_down_and_precedes_key_up(self):
        calls = []

        def send_event(scan_code, extended, key_up):
            calls.append(("up" if key_up else "down", scan_code, extended))
            return True

        def wait(seconds):
            calls.append(("wait", seconds))

        self.assertTrue(
            perform_key_press(0x3B, False, 0.08, send_event, wait)
        )
        self.assertEqual(
            calls,
            [
                ("down", 0x3B, False),
                ("wait", 0.08),
                ("up", 0x3B, False),
            ],
        )

    def test_failed_key_down_is_released_without_waiting(self):
        calls = []

        def send_event(scan_code, extended, key_up):
            calls.append("up" if key_up else "down")
            return key_up

        self.assertFalse(
            perform_key_press(0x3B, False, 0.08, send_event, calls.append)
        )
        self.assertEqual(calls, ["down", "up"])


if __name__ == "__main__":
    unittest.main()
