"""Per-query trace: one event per pipeline stage, with inputs, outputs and timing."""
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field


@dataclass
class Event:
    stage: str
    inputs: dict
    outputs: dict = field(default_factory=dict)
    seconds: float = 0.0


@dataclass
class Trace:
    events: list[Event] = field(default_factory=list)

    @contextmanager
    def stage(self, name: str, **inputs):
        """Record one stage. The caller fills `event.outputs` inside the block."""
        event = Event(stage=name, inputs=inputs)
        start = time.perf_counter()
        try:
            yield event
        finally:
            event.seconds = round(time.perf_counter() - start, 3)
            self.events.append(event)

    def to_dict(self) -> dict:
        return {"events": [asdict(e) for e in self.events]}
