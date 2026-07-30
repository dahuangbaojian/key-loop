import unittest

from key_loop_core import KeyAction, KeyBinding, KeyScheduler


class KeySchedulerTests(unittest.TestCase):
    def setUp(self):
        self.scheduler = KeyScheduler()

    def test_slots_fire_immediately_and_keep_independent_intervals(self):
        bindings = (
            KeyBinding(0, 0x3B, False, 1.0),
            KeyBinding(1, 0x3C, False, 2.0),
        )

        self.assertEqual(
            self.scheduler.tick(0.0, True, bindings, 0.03),
            [
                KeyAction(0x3B, False, True),
                KeyAction(0x3C, False, True),
            ],
        )
        self.assertEqual(self.scheduler.tick(0.02, True, bindings, 0.03), [])
        self.assertEqual(
            self.scheduler.tick(0.03, True, bindings, 0.03),
            [
                KeyAction(0x3B, False, False),
                KeyAction(0x3C, False, False),
            ],
        )
        self.assertEqual(
            self.scheduler.tick(1.0, True, bindings, 0.03),
            [KeyAction(0x3B, False, True)],
        )
        self.assertEqual(
            self.scheduler.tick(2.0, True, bindings, 0.03),
            [
                KeyAction(0x3B, False, False),
                KeyAction(0x3B, False, True),
                KeyAction(0x3C, False, True),
            ],
        )

    def test_stopping_releases_every_held_key(self):
        bindings = (KeyBinding(0, 0x3B, False, 1.0),)
        self.scheduler.tick(0.0, True, bindings, 0.5)

        self.assertEqual(
            self.scheduler.tick(0.1, False, (), 0.5),
            [KeyAction(0x3B, False, False)],
        )
        self.assertEqual(self.scheduler.tick(0.2, False, (), 0.5), [])

    def test_editing_active_slot_releases_old_key_and_presses_new_key(self):
        original = (KeyBinding(0, 0x3B, False, 1.0),)
        updated = (KeyBinding(0, 0x3C, False, 1.0),)
        self.scheduler.tick(0.0, True, original, 0.5)

        self.assertEqual(
            self.scheduler.tick(0.1, True, updated, 0.5),
            [
                KeyAction(0x3B, False, False),
                KeyAction(0x3C, False, True),
            ],
        )

    def test_duplicate_keys_share_one_physical_key_state(self):
        bindings = (
            KeyBinding(0, 0x3B, False, 1.0),
            KeyBinding(1, 0x3B, False, 2.0),
        )

        self.assertEqual(
            self.scheduler.tick(0.0, True, bindings, 0.03),
            [KeyAction(0x3B, False, True)],
        )
        self.assertEqual(
            self.scheduler.tick(0.03, True, bindings, 0.03),
            [KeyAction(0x3B, False, False)],
        )

    def test_interval_edit_starts_a_fresh_interval(self):
        original = (KeyBinding(0, 0x3B, False, 1.0),)
        updated = (KeyBinding(0, 0x3B, False, 10.0),)
        self.scheduler.tick(0.0, True, original, 0.03)
        self.scheduler.tick(0.03, True, original, 0.03)

        self.assertEqual(self.scheduler.tick(0.5, True, updated, 0.03), [])
        self.assertEqual(self.scheduler.tick(10.49, True, updated, 0.03), [])
        self.assertEqual(
            self.scheduler.tick(10.5, True, updated, 0.03),
            [KeyAction(0x3B, False, True)],
        )

    def test_wait_is_bounded_by_next_release(self):
        bindings = (KeyBinding(0, 0x3B, False, 1.0),)
        self.scheduler.tick(0.0, True, bindings, 0.1)

        self.assertAlmostEqual(self.scheduler.next_delay(0.0), 0.05)
        self.assertAlmostEqual(self.scheduler.next_delay(0.08), 0.02)

    def test_interval_shorter_than_hold_does_not_queue_repeats(self):
        bindings = (KeyBinding(0, 0x3B, False, 0.01),)

        self.assertEqual(
            self.scheduler.tick(0.0, True, bindings, 0.03),
            [KeyAction(0x3B, False, True)],
        )
        self.assertEqual(self.scheduler.tick(0.02, True, bindings, 0.03), [])
        self.assertEqual(
            self.scheduler.tick(0.03, True, bindings, 0.03),
            [
                KeyAction(0x3B, False, False),
                KeyAction(0x3B, False, True),
            ],
        )


if __name__ == "__main__":
    unittest.main()
