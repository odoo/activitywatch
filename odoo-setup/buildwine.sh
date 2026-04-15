#!/bin/bash
set -euo pipefail

: "${CARGO_BUILD_TARGET:=x86_64-pc-windows-gnu}"
: "${ODOO_WINDOWS_BUILD:=true}"
: "${SKIP_SERVER_PYTHON:=true}"
: "${WINEPREFIX:=/home/odoo/.wine}"
: "${WINEARCH:=win64}"

PYTHON_DIR="$WINEPREFIX/drive_c/Program Files/Python314"
PYTHON_WIN="C:\\Program Files\\Python314\\python.exe"
PIP_WIN="C:\\Program Files\\Python314\\Scripts\\pip.exe"
AW_SOURCE="/data/build/activitywatch"

export CARGO_BUILD_TARGET ODOO_WINDOWS_BUILD SKIP_SERVER_PYTHON
export WINEPREFIX WINEARCH WINEDEBUG=-all
export XDG_RUNTIME_DIR=/run/user/1000
export DISPLAY=${DISPLAY:-:99}

# Python venv wrappers needed for make subshells
export VIRTUAL_ENV=/home/odoo/awvenv
export PATH="/home/odoo/awvenv/bin:$PATH"
mkdir -p /tmp/awvenv-wrappers
cat > /tmp/awvenv-wrappers/pip << 'EOF'
#!/bin/bash
exec /home/odoo/awvenv/bin/pip "$@"
EOF
cat > /tmp/awvenv-wrappers/python << 'EOF'
#!/bin/bash
exec /home/odoo/awvenv/bin/python "$@"
EOF
chmod +x /tmp/awvenv-wrappers/{pip,python}
export PATH="/tmp/awvenv-wrappers:$PATH"
export PYTHON="wine '$PYTHON_WIN'"
export WINE_PYTHON="wine '$PYTHON_WIN'"

# Xvfb start and stop functions
XVFB_PID=""
_start_xvfb() {
    if ! pgrep -x Xvfb > /dev/null 2>&1; then
        Xvfb $DISPLAY -screen 0 1024x768x24 &
        XVFB_PID=$!
        sleep 2
        echo "[Xvfb] started (PID $XVFB_PID)"
    fi
}

_stop_xvfb() {
    if [[ -n "$XVFB_PID" ]] && kill -0 "$XVFB_PID" 2>/dev/null; then
        kill "$XVFB_PID"
        wait "$XVFB_PID" 2>/dev/null || true
        echo "[Xvfb] stopped"
    fi
}

trap _stop_xvfb EXIT
_start_xvfb

# Wine Python helpers
wine_pip() {
    xvfb-run --auto-servernum wine "$PIP_WIN" "$@"
}

wine_python() {
    xvfb-run --auto-servernum wine "$PYTHON_WIN" "$@"
}

echo "[Wine] initializing prefix..."
wineboot --init 2>/dev/null || true
wineserver -w

echo "[Build] Starting ActivityWatch build..."
export AW_VERSION="0.13.2"
cd "$AW_SOURCE"
make build

echo "[PyInstaller] Installing dependencies ..."
wine_pip install --no-warn-script-location pystray pillow pynput wmi

echo "[PyInstaller] Installing aw packages in Wine..."
wine_pip install --no-warn-script-location \
    "$AW_SOURCE/aw-core" \
    "$AW_SOURCE/aw-client"

echo "[PyInstaller] Building aw-systray-odoo.exe..."
wine_python -m PyInstaller --clean --noconfirm odoo-setup/aw-systray-odoo.spec

echo "[PyInstaller] Building aw-watcher-afk.exe..."
cd "$AW_SOURCE/aw-watcher-afk"
wine_python -m PyInstaller --clean --noconfirm aw-watcher-afk.spec

echo "[PyInstaller] Building aw-watcher-window.exe..."
cd "$AW_SOURCE/aw-watcher-window"
wine_python -m PyInstaller --clean --noconfirm aw-watcher-window.spec

cd "$AW_SOURCE"
STAGING_DIR="$AW_SOURCE/staging-watcher-build"
mkdir -p "$STAGING_DIR"
cp "$AW_SOURCE/dist/aw-systray-odoo.exe" "$STAGING_DIR/"
cp -r "$AW_SOURCE/aw-watcher-afk/dist/aw-watcher-afk" "$STAGING_DIR/"
cp -r "$AW_SOURCE/aw-watcher-window/dist/aw-watcher-window" "$STAGING_DIR/"

export AW_VERSION="odoo-$(date +%Y-%m-%d)"
export AW_PLATFORM=windows
export INNOSETUPDIR="C:\Program Files (x86)\Inno Setup 6"
echo "[Package] Creating package..."
rm -rf "$AW_SOURCE/dist"
mkdir -p "$AW_SOURCE/dist/activitywatch"
for dir in aw-server-rust; do
    make --directory="$AW_SOURCE/$dir" package
    cp -r "$AW_SOURCE/$dir/dist/$dir" "$AW_SOURCE/dist/activitywatch/"
done
cp -r "$STAGING_DIR/aw-watcher-afk" "$AW_SOURCE/dist/activitywatch/"
cp -r "$STAGING_DIR/aw-watcher-window" "$AW_SOURCE/dist/activitywatch/"
cp "$STAGING_DIR/aw-systray-odoo.exe" "$AW_SOURCE/dist/activitywatch/"
rm -rf "$STAGING_DIR"

# Remove problem-causing binaries (see original Makefile)
rm -f "$AW_SOURCE/dist/activitywatch/libdrm.so.2"
rm -f "$AW_SOURCE/dist/activitywatch/libharfbuzz.so.0"
rm -f "$AW_SOURCE/dist/activitywatch/libfontconfig.so.1"
rm -f "$AW_SOURCE/dist/activitywatch/libfreetype.so.6"
rm -rf "$AW_SOURCE/dist/activitywatch/pytz"

# Build zip and installer
bash "$AW_SOURCE/scripts/package/package-all.sh"

echo ""
echo "=== Build finished 🎉 ==="
find "$AW_SOURCE/dist" -name "*.exe" -o -name "*.zip" 2>/dev/null | head -20
