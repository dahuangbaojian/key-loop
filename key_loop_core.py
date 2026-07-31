"""Platform-independent stable scheduling primitives for KeyLoop."""

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Optional, Tuple


@dataclass(frozen=True)
class KeyBinding:
    """One configured key slot."""

    row_id: int
    scan_code: int
    extended: bool
    interval: float

    @property
    def key(self) -> Tuple[int, bool]:
        return self.scan_code, self.extended


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


class KeyScheduler:
    """Choose one due key at a time for stable, serialized key presses."""

    def __init__(self) -> None:
        self._running = False
        self._bindings: Dict[int, KeyBinding] = {}
        self._deadlines: Dict[int, float] = {}

    def next_press(
        self,
        now: float,
        running: bool,
        bindings: Iterable[KeyBinding],
    ) -> Optional[KeyBinding]:
        """Return the next due slot, or ``None`` when nothing is due."""

        current = {binding.row_id: binding for binding in bindings}

        if not running:
            self._running = False
            self._bindings = {}
            self._deadlines = {}
            return None

        if not self._running:
            # Starting always triggers every enabled slot as soon as the
            # stable serial queue can process it.
            self._deadlines = {row_id: now for row_id in current}
        else:
            for row_id in set(self._bindings) - set(current):
                self._deadlines.pop(row_id, None)
            for row_id, binding in current.items():
                previous = self._bindings.get(row_id)
                if previous is None or previous.key != binding.key:
                    self._deadlines[row_id] = now
                elif previous.interval != binding.interval:
                    self._deadlines[row_id] = now + binding.interval

        self._running = True
        self._bindings = current

        due = [
            binding
            for row_id, binding in current.items()
            if now >= self._deadlines.get(row_id, now)
        ]
        if not due:
            return None

        # Oldest deadline first; row_id makes simultaneous slots deterministic.
        binding = min(
            due,
            key=lambda item: (self._deadlines[item.row_id], item.row_id),
        )
        # Base the next interval on the actual dispatch time. Missed periods are
        # skipped instead of being queued into a burst.
        self._deadlines[binding.row_id] = now + binding.interval
        return binding

    def next_delay(self, now: float, maximum: float = 0.05) -> float:
        """Return a bounded wait until the next scheduled press."""

        if not self._running or not self._deadlines:
            return maximum
        return max(0.0, min(maximum, min(self._deadlines.values()) - now))
