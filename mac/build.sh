#!/bin/bash
# Build UseBar.app as a UNIVERSAL (Intel x86_64 + Apple arm64) macOS menu-bar app.
# No third-party deps; the engines are stdlib Python run via the system python3.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BUILD="$HERE/build"
APP="$BUILD/UseBar.app"
BIN="UseBar"

rm -rf "$BUILD"
mkdir -p "$BUILD" "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "==> compiling arm64"
swiftc -O -target arm64-apple-macosx11.0  "$HERE/UseBar.swift" -o "$BUILD/$BIN.arm64"
echo "==> compiling x86_64"
swiftc -O -target x86_64-apple-macosx11.0 "$HERE/UseBar.swift" -o "$BUILD/$BIN.x86_64"
echo "==> lipo -> universal"
lipo -create -output "$APP/Contents/MacOS/$BIN" "$BUILD/$BIN.arm64" "$BUILD/$BIN.x86_64"
lipo -archs "$APP/Contents/MacOS/$BIN"

echo "==> bundling engines"
cp "$ROOT/run.py" "$APP/Contents/Resources/run.py"
mkdir -p "$APP/Contents/Resources/engines"
cp "$ROOT/engines/"*.py "$APP/Contents/Resources/engines/"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>UseBar</string>
  <key>CFBundleDisplayName</key><string>UseBar</string>
  <key>CFBundleIdentifier</key><string>net.agtom.usebar</string>
  <key>CFBundleVersion</key><string>1.0.0</string>
  <key>CFBundleShortVersionString</key><string>1.0.0</string>
  <key>CFBundleExecutable</key><string>UseBar</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# Ad-hoc sign so Gatekeeper/keychain treat it as a stable identity.
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || echo "   (codesign skipped)"

echo "==> built: $APP"
