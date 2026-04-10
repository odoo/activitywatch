#!/usr/bin/env python3

import os
import platform
import subprocess
import sys
import tempfile
import webbrowser

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    import pystray
    from PIL import Image
else:
    import gi
    import psutil
    gi.require_version('Gtk', '3.0')
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3, Gtk
    from PIL import Image


# Detect installation directory
if IS_WINDOWS:
    if getattr(sys, 'frozen', False):
        _install_dir = os.path.dirname(sys.executable)
    else:
        _install_dir = os.path.dirname(os.path.abspath(__file__))
    binaries = [
        os.path.join(_install_dir, "aw-server-rust", "aw-server-rust.exe"),
        os.path.join(_install_dir, "aw-watcher-afk", "aw-watcher-afk.exe"),
        os.path.join(_install_dir, "aw-watcher-window", "aw-watcher-window.exe"),
    ]
else:
    binaries = [
        '/opt/activitywatch/aw-server-rust/aw-server-rust',
        '/opt/activitywatch/awatcher/aw-awatcher',
    ]


def get_icon():
    """Generate an eye icon in Odoo purple color. Returns PIL Image."""
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    for x in range(64):
        for y in range(64):
            pos = (x - 32) ** 2 + (y - 32) ** 2
            if 300 < pos < 900 or pos < 100:
                img.putpixel((x, y), (128, 0, 128, 255))
    return img

def systray_already_running():
    if IS_WINDOWS:
        return False
    else:
        return len([p for p in psutil.process_iter(['cmdline']) if p.info['cmdline'] and p.info['cmdline'][-1].endswith('aw-systray-odoo.py')]) > 1


def notify(message):
    if IS_WINDOWS:
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast("Odoo Activity Watch", message, duration=3)
        except ImportError:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "Odoo Activity Watch", 0)
    else:
        subprocess.run(['notify-send', "Odoo Activity Watch", message], check=False)


class ActivityWatchMonitor:

    def __init__(self, indicator):
        self.procs = []
        self.indicator = indicator

    def check_extension(self):
        if IS_WINDOWS:
            return
        result = subprocess.run(['gnome-extensions', 'list', '--enabled'], capture_output=True, text=True, check=False)
        if 'focused-window-dbus@flexagoon.com' not in result.stdout.split('\n'):
            subprocess.run(['gnome-extensions', 'enable', 'focused-window-dbus@flexagoon.com'], capture_output=True, text=True, check=False)

    def stop_server(self, widget=None):
        for p in self.procs:
            p.poll()
            if p.returncode is None:
                p.terminate()
        self.procs = []

    def open_ui(self, widget=None):
        webbrowser.open("http://127.0.0.1:5600")

    def about(self, widget=None):
        webbrowser.open("https://www.odoo.com/odoo-19-1-release-notes#:~:text=the%20list%20view.-,Timesheets,-ActivityWatch%20integration")

    def start_server(self, widget=None):
        self.check_extension()
        self.stop_server()
        for binary in binaries:
            if not os.path.exists(binary):
                notify(f"Binary not found: {binary}")
                continue
            startupinfo = None
            if IS_WINDOWS:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            b = subprocess.Popen(binary, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
            b.poll()
            if b.returncode is None:
                self.procs.append(b)
            else:
                b.wait()
                notify(f"{binary} not started")

    def on_quit(self, widget=None):
        self.stop_server()
        if IS_WINDOWS:
            if self.indicator:
                self.indicator.stop()
        else:
            Gtk.main_quit()


if IS_WINDOWS:
    def create_indicator(name, icon, menu_items):
        pystray_items = []
        for item in menu_items:
            if item.get("is_separator"):
                pystray_items.append(pystray.Menu.SEPARATOR)
            else:
                pystray_items.append(
                    pystray.MenuItem(
                        item["label"], 
                        item["action"], 
                        default=item.get("default", False)
                    )
                )
        indicator = pystray.Icon(name, icon,name, pystray_items)
        indicator.run()
        return indicator
else:
    def create_indicator(name, icon, menu_items):
        temp_dir = tempfile.gettempdir()
        icon_path = os.path.join(temp_dir, "my-aw-icon.png")
        icon.save(icon_path)
        indicator = AppIndicator3.Indicator.new(name, icon_path, AppIndicator3.IndicatorCategory.APPLICATION_STATUS,)
        indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        menu = Gtk.Menu()
        for item in menu_items:
            if item.get("is_separator"):
                menu.append(Gtk.SeparatorMenuItem())
            else:
                menu_item = Gtk.MenuItem(label=item["label"])
                menu_item.connect("activate", item["action"])
                menu.append(menu_item)
        menu.show_all()
        indicator.set_menu(menu)
        Gtk.main()
        return indicator

if __name__ == '__main__':
    if systray_already_running():
        notify("Systray app is already running !")
        sys.exit(0)
    monitor = ActivityWatchMonitor(None)
    menu_items = [
        {"label": "ActivityWatch UI", "action": monitor.open_ui, "default": True},
        {"label": "Start Server", "action": monitor.start_server},
        {"label": "Stop Server", "action": monitor.stop_server},
        {"label": "About", "action": monitor.about},
        {"is_separator": True},
        {"label": "Exit", "action": monitor.on_quit},
    ]
    icon = get_icon()
    indicator = create_indicator("Odoo ActivityWatch", icon, menu_items)
    monitor.indicator = indicator
