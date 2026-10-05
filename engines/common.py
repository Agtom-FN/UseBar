"""Shared types + the JSON contract every service engine emits.

A service engine returns a Result. Serialized to stdout as JSON, both the macOS
(Swift) and Windows (pystray) GUIs render it identically:

  - `bar`     : compact string for the status item / tooltip, e.g. "S 4%  W 48%  F 34%"
  - `metrics` : rows for the dropdown menu
  - `ok`/`error`

Each Metric:
  key       stable id              ("session","weekly","fable","usage")
  label     full text for the menu ("Session (5h)")
  short     one letter for the bar ("S","W","F","U")
  kind      "pct" | "ratio"
  value     number (percent, or numerator for ratio)
  maximum   denominator for "ratio" (else None)
  resets_at ISO-8601 string or None
  severity  "normal" | "warning" | "critical" | None
"""
from __future__ import annotations
import json
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional, List


def human(n) -> str:
    try:
        d = float(n)
    except Exception:
        return str(n)
    if d >= 1_000_000_000:
        return f"{d / 1_000_000_000:.2f}B"
    if d >= 1_000_000:
        return f"{d / 1_000_000:.1f}M"
    if d >= 1_000:
        return f"{d / 1_000:.1f}K"
    return f"{int(d)}"


@dataclass
class Metric:
    key: str
    label: str
    short: str
    kind: str = "pct"            # "pct" or "ratio"
    value: Optional[float] = None
    maximum: Optional[float] = None
    resets_at: Optional[str] = None
    severity: Optional[str] = None

    def render_value(self) -> str:
        if self.value is None:
            return "–"
        if self.kind == "ratio":
            if self.maximum:
                return f"{int(self.value)}/{int(self.maximum)}"
            return f"{int(self.value)}"
        if self.kind == "count":
            return human(self.value)
        return f"{self.value:.0f}%"

    def bar_token(self) -> str:
        return f"{self.short} {self.render_value()}"


@dataclass
class Result:
    service: str
    ok: bool = True
    metrics: List[Metric] = field(default_factory=list)
    error: Optional[str] = None
    note: Optional[str] = None

    def bar(self) -> str:
        if not self.ok:
            return f"{self.service} ⚠"
        return "  ".join(m.bar_token() for m in self.metrics)

    def to_json(self) -> str:
        return json.dumps({
            "service": self.service,
            "ok": self.ok,
            "error": self.error,
            "note": self.note,
            "bar": self.bar(),
            "metrics": [asdict(m) for m in self.metrics],
        })


def fail(service: str, msg: str) -> Result:
    return Result(service=service, ok=False, error=msg)


def emit(result: Result) -> None:
    sys.stdout.write(result.to_json() + "\n")
