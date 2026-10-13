# -*- mode: python -*-
# vi: set ft=python :

import platform

_system = platform.system()

if _system == "Windows":
    hiddenimports = ['pystray', 'pystray._win32', 'PIL']
    excludes = ['gi', 'psutil', 'win10toast']
elif _system == "Darwin":
    # pystray picks its backend dynamically at runtime, so it must be
    # listed explicitly for PyInstaller's static analysis to bundle it.
    hiddenimports = ['pystray', 'pystray._darwin', 'PIL', 'psutil', 'Foundation']
    excludes = ['gi', 'win10toast']
else:
    hiddenimports = ['PIL', 'psutil']
    excludes = ['pystray', 'win10toast']

a = Analysis(
    ['aw-systray-odoo.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='aw-systray-odoo',
    debug=False,
    strip=False,
    upx=True,
    console=False,
)
