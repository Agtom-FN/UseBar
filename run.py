#!/usr/bin/env python3
"""UseBar engine dispatcher — the single entry point both GUIs call.

  python3 run.py                      -> JSON for the currently selected service
  python3 run.py --service cursor     -> JSON for a specific service (no persist)
  python3 run.py --set-service cursor -> persist selection, print {"service": "..."}
  python3 run.py --list-services      -> {"services": [...], "current": "..."}
"""
import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engines import config          # noqa: E402
from engines.common import emit, fail  # noqa: E402


def engine_for(service):
    if service == "claude":
        from engines import claude
        return claude.fetch
    if service == "cursor":
        from engines import cursor
        return cursor.fetch
    return None


def main(argv):
    if "--list-services" in argv:
        print(json.dumps({"services": config.SERVICES, "current": config.get_service(),
                          "beta": config.BETA}))
        return
    if "--set-service" in argv:
        i = argv.index("--set-service")
        svc = argv[i + 1] if i + 1 < len(argv) else ""
        try:
            config.set_service(svc)
            print(json.dumps({"service": svc, "ok": True}))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}))
        return

    service = config.get_service()
    if "--service" in argv:
        i = argv.index("--service")
        if i + 1 < len(argv):
            service = argv[i + 1]

    fn = engine_for(service)
    if fn is None:
        emit(fail(service, f"unknown service '{service}'"))
        return
    try:
        emit(fn())
    except Exception as e:
        emit(fail(service, f"engine crashed: {e}"))


if __name__ == "__main__":
    main(sys.argv[1:])
