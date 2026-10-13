#!/bin/bash
# Native macOS build script for the Odoo flavor of ActivityWatch.
#
# Unlike Linux/Windows, this canNOT run inside Docker: Apple's toolchain
# (Xcode, iconutil, codesign) only runs on real Apple hardware. Run this
# script directly on a Mac. See odoo-setup/README.md for prerequisites.
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "buildmacos.sh must be run on macOS (found: $(uname -s))." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AW_SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$AW_SOURCE"

ARCH="$(uname -m)"
RELEASE_VERSION="odoo-$(date +%Y-%m-%d)"
APP_NAME="ActivityWatch Odoo.app"
BUNDLE_ID="com.odoo.activitywatch"

# We ship aw-server-rust only: make the root Makefile skip aw-server (Python),
# including its post-build `import aw_server` version check.
export SKIP_SERVER_PYTHON=true

echo "[Check] Verifying required tools are installed..."
missing=()
command -v rustup >/dev/null 2>&1 || missing+=("rustup (https://rustup.rs)")
command -v node >/dev/null 2>&1 || missing+=("node 22.x (e.g. via nvm or brew install node@22)")
command -v python3 >/dev/null 2>&1 || missing+=("python3.10+")
command -v poetry >/dev/null 2>&1 || missing+=("poetry (pip install poetry)")
xcode-select -p >/dev/null 2>&1 || missing+=("Xcode Command Line Tools (xcode-select --install)")
if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Missing prerequisites:" >&2
    printf ' - %s\n' "${missing[@]}" >&2
    exit 1
fi

rustup toolchain install nightly
rustup default nightly

echo "[Venv] Setting up build virtualenv..."
VENV_DIR="$AW_SOURCE/.odoo-macos-build-venv"
python3 -m venv "$VENV_DIR"
export VIRTUAL_ENV="$VENV_DIR"
export PATH="$VENV_DIR/bin:$PATH"
pip install --upgrade pip poetry pyinstaller pystray pillow psutil

echo "[Build] Building ActivityWatch submodules..."
BUILD_SUBMODULES='aw-core aw-client aw-server-rust aw-watcher-afk aw-watcher-window'
export AW_VERSION="0.13.2"
make build SUBMODULES="$BUILD_SUBMODULES"

echo "[PyInstaller] Building aw-systray-odoo..."
pyinstaller --clean --noconfirm odoo-setup/aw-systray-odoo.spec
STAGING_DIR="$AW_SOURCE/staging-systray-build"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
cp dist/aw-systray-odoo "$STAGING_DIR/"

echo "[Package] Packaging submodules..."
# Mirrors buildwine.sh: package each submodule directly (instead of the root
# `make package` target) so dist/activitywatch/ can be fully assembled,
# including aw-systray-odoo, before package-all.sh zips it up.
rm -rf dist
mkdir -p dist/activitywatch
for dir in aw-server-rust aw-watcher-afk aw-watcher-window; do
    make --directory="$dir" package
    cp -r "$dir/dist/$dir" dist/activitywatch/
done
cp "$STAGING_DIR/aw-systray-odoo" dist/activitywatch/aw-systray-odoo
rm -rf "$STAGING_DIR"

export AW_VERSION="$RELEASE_VERSION"
export AW_PLATFORM=macos
bash scripts/package/package-all.sh

echo "[Icon] Generating logo.icns from the systray icon..."
# Render the same purple ring as the menu bar icon, so the .app (and thus
# its notifications) carries the Odoo icon instead of the ActivityWatch one.
ICONSET="build/odoo-logo.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
python3 - "$ICONSET" <<'PYEOF'
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("aw_systray_odoo", "odoo-setup/aw-systray-odoo.py")
systray = importlib.util.module_from_spec(spec)
spec.loader.exec_module(systray)
icon, _ = systray.get_icon(1024)
for size in (16, 32, 128, 256, 512):
    icon.resize((size, size)).save(f"{sys.argv[1]}/icon_{size}x{size}.png")
    icon.resize((size * 2, size * 2)).save(f"{sys.argv[1]}/icon_{size}x{size}@2x.png")
PYEOF
iconutil --convert icns "$ICONSET" --output build/odoo-logo.icns

echo "[Bundle] Assembling ${APP_NAME}..."
APP="dist/${APP_NAME}"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
# Only the main executable goes in Contents/MacOS. The server and watchers
# are PyInstaller folders full of data files (and a Python.framework), which
# codesign rejects inside Contents/MacOS but seals fine as Resources.
cp dist/activitywatch/aw-systray-odoo "$APP/Contents/MacOS/aw-systray-odoo"
cp -r dist/activitywatch/aw-server-rust "$APP/Contents/Resources/"
cp -r dist/activitywatch/aw-watcher-afk "$APP/Contents/Resources/"
cp -r dist/activitywatch/aw-watcher-window "$APP/Contents/Resources/"
cp build/odoo-logo.icns "$APP/Contents/Resources/logo.icns"
sed "s/__VERSION__/${RELEASE_VERSION}/" odoo-setup/macos/Info.plist > "$APP/Contents/Info.plist"

if [[ -n "${APPLE_PERSONALID:-}" ]]; then
    echo "[Sign] Codesigning ${APP_NAME} with identity: ${APPLE_PERSONALID}"
    codesign --deep --force --options runtime \
        --entitlements scripts/package/entitlements.plist \
        --sign "$APPLE_PERSONALID" "$APP"
else
    # Ad-hoc sign the bundle (not --deep: the nested binaries are already
    # ad-hoc signed by PyInstaller/the linker). Without a valid bundle
    # signature, macOS privacy (TCC) identifies the app by executable path
    # instead of bundle id, so the Accessibility grant made in System
    # Settings never matches and aw-watcher-window keeps prompting.
    echo "[Sign] APPLE_PERSONALID not set, ad-hoc signing (build will be Gatekeeper-unsigned)."
    codesign --force --sign - --identifier "$BUNDLE_ID" "$APP"
    codesign --verify --strict --verbose=2 "$APP"
fi

echo "[Package] Building .pkg installer..."
PKGROOT="dist/pkgroot"
rm -rf "$PKGROOT"
mkdir -p "$PKGROOT/Applications" "$PKGROOT/Library/LaunchAgents"
cp -r "$APP" "$PKGROOT/Applications/"
cp odoo-setup/macos/com.odoo.activitywatch.plist "$PKGROOT/Library/LaunchAgents/"

# By default pkgbuild marks bundles as relocatable: Installer then looks for
# an existing app with the same bundle id anywhere on disk (e.g. the copy in
# dist/ on the build machine) and upgrades it in place instead of installing
# into /Applications. The LaunchAgent hardcodes /Applications, so forbid it.
COMPONENT_PLIST="dist/component.plist"
pkgbuild --analyze --root "$PKGROOT" "$COMPONENT_PLIST"
plutil -replace 0.BundleIsRelocatable -bool NO "$COMPONENT_PLIST"

PKG_UNSIGNED="dist/activitywatch-${RELEASE_VERSION}-macos-${ARCH}.pkg"
pkgbuild --root "$PKGROOT" \
    --component-plist "$COMPONENT_PLIST" \
    --identifier "$BUNDLE_ID" \
    --version "$RELEASE_VERSION" \
    --scripts "$SCRIPT_DIR/macos" \
    --install-location / \
    "$PKG_UNSIGNED"

if [[ -n "${APPLE_INSTALLER_IDENTITY:-}" ]]; then
    echo "[Sign] Signing .pkg with installer identity: ${APPLE_INSTALLER_IDENTITY}"
    PKG_SIGNED="dist/activitywatch-${RELEASE_VERSION}-macos-${ARCH}-signed.pkg"
    productsign --sign "$APPLE_INSTALLER_IDENTITY" "$PKG_UNSIGNED" "$PKG_SIGNED"
    mv -f "$PKG_SIGNED" "$PKG_UNSIGNED"
    # NOTE: notarization (xcrun notarytool submit / stapler) is not wired up
    # yet. Without it, Gatekeeper will still warn on first launch even for
    # a signed .pkg. See odoo-setup/README.md.
else
    echo "[Sign] APPLE_INSTALLER_IDENTITY not set, skipping .pkg signing."
fi

rm -rf "$PKGROOT" "$VENV_DIR" "$COMPONENT_PLIST"

echo ""
echo "=== Build finished ==="
ls -l "$PKG_UNSIGNED"
