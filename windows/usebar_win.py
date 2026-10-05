#!/usr/bin/env python3
"""UseBar (Windows / cross-platform tray) — same engines, pystray GUI.

Shows a tray icon for the selected service; the tooltip carries the compact
readout (e.g. "Claude  S 4%  W 48%  F 34%" or "Cursor  U 123/500"), and the
right-click menu lists each metric, lets you switch service, refresh, or quit.

Engines are imported in-process (stdlib only), so a PyInstaller build needs no
external python. Requires: pystray, Pillow  (GUI only).
"""
import os
import sys
import threading
import math

# make the repo root importable whether run from source or frozen
if getattr(sys, "frozen", False):
    ROOT = os.path.dirname(sys.executable)
else:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engines import config                       # noqa: E402
from engines import claude as claude_engine      # noqa: E402
from engines import cursor as cursor_engine      # noqa: E402

import pystray                                    # noqa: E402
from PIL import Image, ImageDraw                  # noqa: E402

REFRESH_SECONDS = 120
ENGINES = {"claude": claude_engine.fetch, "cursor": cursor_engine.fetch}


def claude_image(size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    rays = 12
    r_out = size * 0.46
    r_in = size * 0.06
    w = size * 0.09
    col = (217, 119, 87, 255)  # Claude-ish terracotta
    for i in range(rays):
        a = (i / rays) * 2 * math.pi
        ca, sa = math.cos(a), math.sin(a)
        px, py = -sa, ca
        tip = (cx + ca * r_out, cy + sa * r_out)
        b1 = (cx + ca * r_in + px * w, cy + sa * r_in + py * w)
        b2 = (cx + ca * r_in - px * w, cy + sa * r_in - py * w)
        d.polygon([tip, b1, b2], fill=col)
    d.ellipse([cx - w, cy - w, cx + w, cy + w], fill=col)
    return img


def cursor_image(size=64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size
    d.polygon([(s*0.18, s*0.1), (s*0.18, s*0.8), (s*0.38, s*0.6),
               (s*0.5, s*0.88), (s*0.6, s*0.84), (s*0.48, s*0.56),
               (s*0.74, s*0.56)], fill=(90, 160, 240, 255))
    return img


class UseBarTray:
    def __init__(self):
        self.service = config.get_service()
        self.result = None
        self.icon = pystray.Icon("UseBar", self._image(), "UseBar", menu=self._menu())

    def _image(self):
        return cursor_image() if self.service == "cursor" else claude_image()

    def _name(self, svc=None):
        svc = svc or self.service
        base = "Cursor" if svc == "cursor" else "Claude"
        return f"{base} (beta)" if config.is_beta(svc) else base

    def _title(self):
        name = self._name()
        if not self.result or not self.result.ok:
            err = (self.result.error if self.result else "loading…") or "unavailable"
            return f"{name}  ⚠ {err}"
        return f"{name}  " + "  ".join(m.bar_token() for m in self.result.metrics)

    def _metric_items(self):
        items = []
        if self.result and self.result.ok:
            for m in self.result.metrics:
                reset = ""
                if m.resets_at:
                    reset = f"  · resets {m.resets_at[11:16]}"
                items.append(pystray.MenuItem(f"{m.label}: {m.render_value()}{reset}",
                                              None, enabled=False))
            if self.result.note:
                items.append(pystray.MenuItem(self.result.note, None, enabled=False))
        elif self.result:
            items.append(pystray.MenuItem(self.result.error or "unavailable", None, enabled=False))
        else:
            items.append(pystray.MenuItem("loading…", None, enabled=False))
        return items

    def _menu(self):
        def make_switch(svc):
            return lambda icon, item: self.switch(svc)
        svc_items = [
            pystray.MenuItem(
                self._name(s),
                make_switch(s),
                checked=(lambda item, s=s: self.service == s),
                radio=True,
            ) for s in config.SERVICES
        ]
        return pystray.Menu(
            *self._metric_items(),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Service", pystray.Menu(*svc_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Refresh now", lambda icon, item: self.refresh()),
            pystray.MenuItem("Quit UseBar", lambda icon, item: icon.stop()),
        )

    def switch(self, svc):
        self.service = svc
        config.set_service(svc)
        self.refresh()

    def refresh(self):
        try:
            self.result = ENGINES[self.service]()
        except Exception as e:
            from engines.common import fail
            self.result = fail(self.service, f"engine crashed: {e}")
        self.icon.icon = self._image()
        self.icon.title = self._title()
        self.icon.menu = self._menu()
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def _loop(self):
        import time
        while True:
            self.refresh()
            time.sleep(REFRESH_SECONDS)

    def run(self):
        threading.Thread(target=self._loop, daemon=True).start()
        self.icon.run()


if __name__ == "__main__":
    UseBarTray().run()
