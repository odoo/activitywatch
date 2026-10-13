# ActivityWatch Odoo Package Build

Build script for Odoo version of ActivityWatch packages for Linux (Debian/Ubuntu), Windows, and macOS.

## Requirements

- Docker (for Linux/Windows builds only — see [macOS](#macos-build) below)
- `realpath` (coreutils)
- Sufficient disk space (~2GB for Docker images + build artifacts)

## Usage

```bash
./buildpackage.sh <distro> [package_name]
```

### Arguments

| Argument | Description | Default |
|---|---|---|
| `distro` | Target platform (`noble`, `jammy`, `windows`, `macos`) | `noble` |
| `package_name` | Output package name (Linux only) | `activitywatch-odoo-<distro>` |

### Examples

```bash
# Build Ubuntu 24.04 package
./buildpackage.sh noble

# Build Ubuntu 22.04 package
./buildpackage.sh jammy

# Build Windows installer
./buildpackage.sh windows

# Build macOS installer (must run on an actual Mac, see below)
./buildpackage.sh macos

# Custom package name
./buildpackage.sh jammy activitywatch-custom
```

## Outputs

After a successful build, artifacts are available in `odoo-setup/dist/`:

| Platform | Output |
|---|---|
| Linux | `activitywatch-odoo-<distro>.deb` |
| Windows | `activitywatch-odoo-YYYY-MM-DD-windows-x86_64-setup.exe` + `.zip` |
| macOS | `activitywatch-odoo-YYYY-MM-DD-macos-<arch>.pkg` + `.zip` |

## macOS build

Apple's build toolchain (Xcode, `codesign`, `iconutil`, `pkgbuild`) only runs on real Apple
hardware — it cannot be virtualized in Docker the way the Linux/Windows builds are. So there is
no `Dockerfile_macos`; instead `./buildpackage.sh macos` execs `buildmacos.sh` directly, which
must be run **on a Mac** (Apple Silicon or Intel — it builds for the host's own architecture).

### Prerequisites (install once, on the Mac doing the build)

- Xcode Command Line Tools: `xcode-select --install`
- [rustup](https://rustup.rs)
- Node.js 22.x (e.g. via [nvm](https://github.com/nvm-sh/nvm) or `brew install node@22`)
- Python 3.10+ with `poetry` (`pip install poetry`)

`buildmacos.sh` checks for these up front and exits with a clear message if any are missing —
it does not install system-level tooling on your behalf.

### What it builds

- `aw-server-rust`, `aw-watcher-afk`, `aw-watcher-window` (built/packaged the same way upstream
  ActivityWatch already does for its own macOS releases).
- `aw-systray-odoo` (the Odoo menu-bar app, same script as Windows) — built via PyInstaller
  using `pystray`'s macOS backend, since GTK/AppIndicator3 isn't available there.
- Everything is assembled into `ActivityWatch Odoo.app` and autostarts at login via a
  LaunchAgent (`odoo-setup/macos/com.odoo.activitywatch.plist`), installed to
  `/Library/LaunchAgents/` by the `.pkg`'s `postinstall` script — this is the macOS equivalent
  of the `.desktop` autostart entry on Linux / startup-folder shortcut on Windows.

### Code signing / notarization

Unsigned builds work but trigger a Gatekeeper warning on first launch (right-click → Open).
To sign, set these before running the build:

- `APPLE_PERSONALID` — Developer ID Application identity, used to codesign the `.app`
  (same env var upstream ActivityWatch's own `aw.spec`/CI use).
- `APPLE_INSTALLER_IDENTITY` — Developer ID Installer identity, used to sign the `.pkg`
  (via `productsign`).

Notarization (`xcrun notarytool submit` + `stapler`) is **not** wired up yet — a signed but
unnotarized `.pkg` will still be flagged by Gatekeeper. That's the next step once Odoo's Apple
Developer credentials are available for this build.

## Troubleshooting

### Docker permission errors

Ensure your user is in the `docker` group:

```bash
sudo usermod -aG docker $USER
```
