import asyncio
import json
import time
from dataclasses import dataclass, field

FRAME_TELEPROMPTER = 0x03


@dataclass
class TeleprompterState:
    """A live room session, deliberately excluded from document snapshots."""

    active: bool = False
    running: bool = False
    speed: int = 140
    position: float = 0
    updated_at: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def current_position(self) -> float:
        elapsed = time.monotonic() - self.updated_at if self.running else 0
        return self.position + elapsed * self.speed / 60

    def command(self, payload: bytes) -> bool:
        if payload not in {b"open", b"play", b"pause", b"faster", b"slower", b"restart", b"cancel"} or (
            not self.active and payload != b"open"
        ):
            return False

        self.position = self.current_position()
        self.updated_at = time.monotonic()
        if payload == b"open":
            if not self.active:
                self.active = True
                self.position = 0
        elif payload == b"play":
            self.running = True
        elif payload == b"pause":
            self.running = False
        elif payload == b"faster":
            self.speed = min(300, self.speed + 20)
        elif payload == b"slower":
            self.speed = max(40, self.speed - 20)
        elif payload == b"restart":
            self.position = 0
            self.running = True
        elif payload == b"cancel":
            self.active = False
            self.running = False
            self.position = 0
        return True

    def payload(self) -> bytes:
        return json.dumps(
            {
                "active": self.active,
                "running": self.running,
                "speed": self.speed,
                "position": self.current_position(),
            }
        ).encode()
