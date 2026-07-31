"""Platform-independent scheduling primitives for KeyLoop."""

from typing import Callable


def perform_key_press(
    scan_code: int,
    extended: bool,
    hold_s: float,
    send_event: Callable[[int, bool, bool], bool],
    wait: Callable[[float], object],
) -> bool:
    """Send a complete press whose hold starts after key-down dispatch."""

    pressed = send_event(scan_code, extended, False)
    if pressed:
        wait(hold_s)
    released = send_event(scan_code, extended, True)
    return pressed and released


class BuffComboScheduler:
    """Schedule one complete Buff combo at a time."""

    def __init__(self) -> None:
        self._running = False
        self._enabled = False
        self._interval = 0.0
        self._deadline = None

    def should_start(
        self,
        now: float,
        running: bool,
        enabled: bool,
        interval: float,
    ) -> bool:
        """Return True once when the enabled combo becomes due."""

        if not running:
            self._running = False
            self._enabled = False
            self._deadline = None
            return False

        if not self._running:
            # Each run starts with one immediate Buff combo.
            self._deadline = now if enabled else None
        else:
            if not enabled:
                self._deadline = None
            elif not self._enabled:
                self._deadline = now
            elif interval != self._interval:
                self._deadline = now + interval

        self._running = True
        self._enabled = enabled
        self._interval = interval

        if enabled and self._deadline is not None and now >= self._deadline:
            # No new combo is scheduled until the current one reports complete.
            self._deadline = None
            return True
        return False

    def complete(self, now: float) -> None:
        """Start the configured interval after the whole combo finishes."""

        if self._running and self._enabled:
            self._deadline = now + self._interval

    def next_delay(self, now: float, maximum: float = 0.05) -> float:
        """Return a bounded wait until the next combo."""

        if not self._running or self._deadline is None:
            return maximum
        return max(0.0, min(maximum, self._deadline - now))
