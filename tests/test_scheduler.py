import unittest

from key_loop_core import BuffComboScheduler, perform_key_press


class BuffComboSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.scheduler = BuffComboScheduler()

    def test_start_runs_enabled_combo_immediately(self):
        self.assertTrue(self.scheduler.should_start(0.0, True, True, 1200.0))
        self.assertFalse(self.scheduler.should_start(0.1, True, True, 1200.0))

    def test_interval_starts_after_combo_completes(self):
        self.scheduler.should_start(0.0, True, True, 1200.0)
        self.scheduler.complete(30.0)

        self.assertFalse(
            self.scheduler.should_start(1229.9, True, True, 1200.0)
        )
        self.assertTrue(
            self.scheduler.should_start(1230.0, True, True, 1200.0)
        )

    def test_enabling_first_buff_runs_combo_immediately(self):
        self.assertFalse(
            self.scheduler.should_start(0.0, True, False, 1200.0)
        )
        self.assertTrue(
            self.scheduler.should_start(1.0, True, True, 1200.0)
        )

    def test_interval_edit_starts_a_fresh_interval(self):
        self.scheduler.should_start(0.0, True, True, 1200.0)
        self.scheduler.complete(30.0)

        self.assertFalse(
            self.scheduler.should_start(100.0, True, True, 600.0)
        )
        self.assertFalse(
            self.scheduler.should_start(699.9, True, True, 600.0)
        )
        self.assertTrue(
            self.scheduler.should_start(700.0, True, True, 600.0)
        )

    def test_restart_runs_combo_immediately(self):
        self.scheduler.should_start(0.0, True, True, 1200.0)

        self.assertFalse(
            self.scheduler.should_start(0.1, False, True, 1200.0)
        )
        self.assertTrue(
            self.scheduler.should_start(0.2, True, True, 1200.0)
        )

    def test_wait_is_bounded_by_next_deadline(self):
        self.scheduler.should_start(0.0, True, True, 1.0)
        self.scheduler.complete(0.0)

        self.assertAlmostEqual(self.scheduler.next_delay(0.0), 0.05)
        self.assertAlmostEqual(self.scheduler.next_delay(0.98), 0.02)


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
