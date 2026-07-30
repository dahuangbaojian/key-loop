"""Platform-independent scheduling primitives for KeyLoop."""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


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


@dataclass(frozen=True)
class KeyAction:
    """A key-down or key-up action produced by the scheduler."""

    scan_code: int
    extended: bool
    key_down: bool


class KeyScheduler:
    """Schedule independent key slots without blocking for key hold times.

    The scheduler only calculates actions. The caller owns the clock and sends
    the resulting actions to the operating system.
    """

    def __init__(self) -> None:
        self._running = False
        self._bindings: Dict[int, KeyBinding] = {}
        self._deadlines: Dict[int, float] = {}
        self._active: Dict[int, Tuple[Tuple[int, bool], float]] = {}
        self._key_refcounts: Dict[Tuple[int, bool], int] = {}

    def tick(
        self,
        now: float,
        running: bool,
        bindings: Iterable[KeyBinding],
        hold_s: float,
    ) -> List[KeyAction]:
        """Advance the scheduler and return key actions due at ``now``."""

        current = {binding.row_id: binding for binding in bindings}
        actions: List[KeyAction] = []

        # Release completed, disabled, or changed slots first.
        for row_id, (held_key, release_at) in list(self._active.items()):
            binding = current.get(row_id)
            key_changed = binding is None or binding.key != held_key
            if not running or key_changed or now >= release_at:
                self._release(row_id, actions)

        if not running:
            self._running = False
            self._bindings = {}
            self._deadlines = {}
            return actions

        if not self._running:
            # Starting always triggers every enabled slot immediately.
            self._deadlines = {row_id: now for row_id in current}
        else:
            for row_id in set(self._bindings) - set(current):
                self._deadlines.pop(row_id, None)
            for row_id, binding in current.items():
                previous = self._bindings.get(row_id)
                if previous is None or previous.key != binding.key:
                    # Newly enabled slots and key changes fire immediately.
                    self._deadlines[row_id] = now
                elif previous.interval != binding.interval:
                    # An interval edit starts a fresh interval instead of
                    # producing an unexpected immediate repeat.
                    self._deadlines[row_id] = now + binding.interval

        self._running = True
        self._bindings = current

        for row_id in sorted(current):
            if row_id in self._active:
                continue
            binding = current[row_id]
            deadline = self._deadlines.get(row_id, now)
            if now < deadline:
                continue
            self._acquire(binding, now + hold_s, actions)
            # Base the next interval on the actual firing time. This avoids
            # catch-up bursts after the machine has been suspended or busy.
            self._deadlines[row_id] = now + binding.interval

        return actions

    def next_delay(self, now: float, maximum: float = 0.05) -> float:
        """Return a bounded wait until the next known scheduler deadline."""

        deadlines = [release_at for _, release_at in self._active.values()]
        if self._running:
            deadlines.extend(
                deadline
                for row_id, deadline in self._deadlines.items()
                if row_id not in self._active
            )
        if not deadlines:
            return maximum
        return max(0.0, min(maximum, min(deadlines) - now))

    def _acquire(
        self,
        binding: KeyBinding,
        release_at: float,
        actions: List[KeyAction],
    ) -> None:
        key = binding.key
        count = self._key_refcounts.get(key, 0)
        if count == 0:
            actions.append(
                KeyAction(binding.scan_code, binding.extended, key_down=True)
            )
        self._key_refcounts[key] = count + 1
        self._active[binding.row_id] = (key, release_at)

    def _release(self, row_id: int, actions: List[KeyAction]) -> None:
        key, _ = self._active.pop(row_id)
        count = self._key_refcounts[key] - 1
        if count == 0:
            self._key_refcounts.pop(key)
            actions.append(KeyAction(key[0], key[1], key_down=False))
        else:
            self._key_refcounts[key] = count
