# UseBar

A tiny menu-bar / system-tray app that shows your AI-tool usage at a glance.

- **Claude** — the live `/usage` rate-limit percentages: **S**ession (5h), **W**eekly (7d), and **F**able (7d).
- **Cursor** *(beta)* — the monthly fast-request quota: **U**sage (Cursor has no weekly window). The Cursor dashboard API is undocumented, so this is marked beta and its shape may change.

Pick which service to show from the menu. macOS (Intel **and** Apple Silicon) and Windows.

```
  ✳ S 6%  W 49%  F 34%          ➜ (cursor)   U 123/500
```

## How it works

A small shared Python **engine** (standard library only — no pip packages) reads
your usage and emits a simple JSON contract. Thin native GUIs render it:

- **macOS** — a Swift `NSStatusBar` app (`mac/UseBar.swift`), built as a universal binary.
- **Windows** — a `pystray` tray app (`windows/usebar_win.py`).

### Where the data comes from

| Service | Source | Auth |
|---|---|---|
| Claude | `GET https://api.anthropic.com/api/oauth/usage` (the same endpoint Claude Code's `/usage` uses) | your Claude Code OAuth token |
| Cursor | Cursor's dashboard usage API | your local Cursor session token |

**Privacy:** UseBar reads tokens that are *already on your machine* (macOS Keychain
item `Claude Code-credentials`; Cursor's local `state.vscdb`) and talks **only** to
the official Anthropic / Cursor endpoints. Nothing is sent anywhere else, and the
tokens never leave your computer. If a token is missing or expired the app says so
and (for Claude) falls back to **local token volume** computed from
`~/.claude/projects/**/*.jsonl` with no network at all.

## Install

### macOS

```bash
./mac/build.sh            # produces mac/build/UseBar.app (universal x86_64 + arm64)
open mac/build/UseBar.app
```

First run with Cursor selected, macOS may prompt to allow Keychain access — click
**Always Allow**. To start at login: System Settings → General → Login Items → add
`UseBar.app`.

Requires a `python3` on PATH (macOS ships one with the Command Line Tools; Homebrew
python also works). No Python packages are needed on macOS.

### Windows

```powershell
# from the repo root
powershell -ExecutionPolicy Bypass -File windows\build.ps1   # -> dist\UseBar.exe
```

Or run from source:

```powershell
python -m pip install -r windows\requirements.txt
python windows\usebar_win.py
```

The tray icon's tooltip shows the readout; right-click for the breakdown, to switch
service, refresh, or quit.

## Switching service

Use the **Service** menu (macOS) / **Service** submenu (Windows). The choice is saved to:

- macOS: `~/Library/Application Support/UseBar/config.json`
- Windows: `%APPDATA%\UseBar\config.json`

## Repo layout

```
engines/        shared, stdlib-only usage engines + JSON contract
  common.py     Metric/Result types, the JSON schema both GUIs render
  config.py     which service is selected (cross-platform)
  claude.py     Claude live /usage %  (+ local-volume fallback)
  cursor.py     Cursor monthly usage
run.py          dispatcher both GUIs call
mac/            Swift menu-bar app + universal build.sh
windows/        pystray tray app + build.ps1
```

## License

MIT — see [LICENSE](LICENSE).
