#!/usr/bin/bash
set -xe

cd "$(dirname "$(realpath "$0")")" || exit
mkdir -p dist

DISTRO_NAME="${1:-${DISTRO_NAME:-"archlinux"}}"
PACKAGE_NAME="${2:-${PACKAGE_NAME:-"activitywatch-odoo"}}"

DOCKER_FILE="Dockerfile_${DISTRO_NAME}"
DOCKER_TAG="${DISTRO_NAME}-awbuilder"

# Build the Arch builder image
docker build -t "${DOCKER_TAG}" . -f "${DOCKER_FILE}" --build-arg=USID=$(id -u) --build-arg=GRID=$(id -g)

# Run the build execution pipeline
docker run --rm \
    -v "$(realpath ../):/data/build/activitywatch" \
    -w "/data/build/activitywatch" \
    -t "${DOCKER_TAG}:latest" \
    /bin/bash -c "
        set -e # Absolute safety switch: crash out immediately if any command fails

        # 1. Clean up old states
        make clean

        # 2. Compile and package the zip
        POETRY_VIRTUALENVS_CREATE=false make build SUBMODULES='aw-core aw-client aw-qt aw-server aw-server-rust aw-watcher-afk aw-watcher-window awatcher'
        POETRY_VIRTUALENVS_CREATE=false make package SUBMODULES='aw-core aw-client aw-qt aw-server aw-server-rust aw-watcher-afk aw-watcher-window awatcher'

        # 3. Create the packaging directory safely after compilation
        mkdir -p dist/arch-build

        echo 'Preparing Arch Linux PKGBUILD...'
        cat << 'EOF' > dist/arch-build/PKGBUILD
pkgname=${PACKAGE_NAME}
pkgver=1.0.0
pkgrel=1
pkgdesc=\"ActivityWatch fork for Odoo Custom Deployment\"
arch=('x86_64')
url=\"https://github.com/your-fork/activitywatch\"
license=('MPL-2.0')
depends=('glib2' 'libxkbcommon' 'openssl' 'python')
source=()

package() {
    # Using absolute paths inside Docker completely eliminates pathing errors
    mkdir -p \"\$pkgdir/opt\"
    unzip -o /data/build/activitywatch/dist/activitywatch-*-linux-x86_64.zip -d \"\$pkgdir/opt/\"

    mkdir -p \"\$pkgdir/usr/share/gnome-shell/extensions/\"
    unzip -o /data/build/activitywatch/odoo-setup/focused-window-dbus-archlinux.zip -d \"\$pkgdir/usr/share/gnome-shell/extensions/\"

    cp /data/build/activitywatch/odoo-setup/aw-systray-odoo.py \"\$pkgdir/opt/activitywatch/aw-systray-odoo.py\"

    mkdir -p \"\$pkgdir/etc/xdg/autostart/\"
    mkdir -p \"\$pkgdir/usr/share/applications/\"
    cp /data/build/activitywatch/odoo-setup/activitywatch-odoo.desktop \"\$pkgdir/etc/xdg/autostart/\"
    cp /data/build/activitywatch/odoo-setup/activitywatch-odoo.desktop \"\$pkgdir/usr/share/applications/\"

    mkdir -p \"\$pkgdir/usr/share/licenses/\$pkgname/\"
    if [ -f /data/build/activitywatch/LICENSE ]; then
        cp /data/build/activitywatch/LICENSE \"\$pkgdir/usr/share/licenses/\$pkgname/\"
    elif [ -f /data/build/activitywatch/LICENSE.txt ]; then
        cp /data/build/activitywatch/LICENSE.txt \"\$pkgdir/usr/share/licenses/\$pkgname/\"
    fi
}
EOF

        echo 'Building Arch Linux Package via makepkg...'
        cd dist/arch-build
        makepkg --nodeps --noprepare --nocheck
        mv *.pkg.tar.zst ../
    "
