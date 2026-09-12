from __future__ import annotations

import threading
from collections import Counter


class Metrics:
    def __init__(self) -> None:
        self._counter: Counter[str] = Counter()
        self._lock = threading.Lock()

    def inc(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counter[name] += amount

    def render_prometheus(self) -> str:
        lines = ["# TYPE osiris_fusion_counter counter"]
        with self._lock:
            for name, value in sorted(self._counter.items()):
                safe = name.replace("-", "_").replace(".", "_")
                lines.append(f'osiris_fusion_counter{{name="{safe}"}} {value}')
        return "\n".join(lines) + "\n"


metrics = Metrics()
