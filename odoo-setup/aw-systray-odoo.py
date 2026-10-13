#!/usr/bin/env python3

import os
import platform
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
# Windows and macOS ship as a frozen PyInstaller binary with no system tray
# toolkit available, so both use pystray. Linux uses AppIndicator3 (GTK),
# provided by the distro, since it runs as a plain python3 script.
USE_PYSTRAY = IS_WINDOWS or IS_MACOS

if USE_PYSTRAY:
    import pystray
    from PIL import Image
    if IS_MACOS:
        import psutil
else:
    import gi
    import psutil
    gi.require_version('Gtk', '3.0')
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3, Gtk
    from PIL import Image


# Detect installation directory
if USE_PYSTRAY:
    if getattr(sys, 'frozen', False):
        _install_dir = os.path.dirname(sys.executable)
        if IS_MACOS:
            # Inside "ActivityWatch Odoo.app": Contents/MacOS -> Contents/Resources
            _install_dir = os.path.join(os.path.dirname(_install_dir), "Resources")
    else:
        _install_dir = os.path.dirname(os.path.abspath(__file__))
    if IS_WINDOWS:
        binaries = [
            os.path.join(_install_dir, "aw-server-rust", "aw-server-rust.exe"),
            os.path.join(_install_dir, "aw-watcher-afk", "aw-watcher-afk.exe"),
            os.path.join(_install_dir, "aw-watcher-window", "aw-watcher-window.exe"),
        ]
    else:
        # macOS: binaries live in "ActivityWatch Odoo.app/Contents/Resources/",
        # see odoo-setup/buildmacos.sh.
        binaries = [
            os.path.join(_install_dir, "aw-server-rust", "aw-server-rust"),
            os.path.join(_install_dir, "aw-watcher-afk", "aw-watcher-afk"),
            os.path.join(_install_dir, "aw-watcher-window", "aw-watcher-window"),
        ]
else:
    binaries = [
        '/opt/activitywatch/aw-server-rust/aw-server-rust',
        '/opt/activitywatch/awatcher/aw-awatcher',
    ]


def get_icon(size=64):
    """Generate an eye icon in Odoo purple color. Returns PIL Image.

    `size` other than 64 is used by buildmacos.sh to render the .app icon.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img_stop = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    scale = (size / 64) ** 2
    for x in range(size):
        for y in range(size):
            pos = (x - size / 2) ** 2 + (y - size / 2) ** 2
            if 300 * scale < pos < 900 * scale:
                img.putpixel((x, y), (128, 0, 128, 255))
                img_stop.putpixel((x, y), (128, 128, 128, 255))

    return img, img_stop


def systray_already_running():
    if IS_WINDOWS:
        return False
    if IS_MACOS:
        # Frozen PyInstaller binary, so the process name is the exe itself,
        # not a "...aw-systray-odoo.py" cmdline like the Linux script.
        # A onefile build runs as a bootloader parent + child with the same
        # name, so ignore both our own pid and our parent's.
        exe_name = os.path.basename(sys.executable) if getattr(sys, 'frozen', False) else 'aw-systray-odoo.py'
        own_pids = {os.getpid(), os.getppid()}
        return any(p.info['name'] == exe_name and p.pid not in own_pids for p in psutil.process_iter(['name']))
    return len([p for p in psutil.process_iter(['cmdline']) if p.info['cmdline'] and p.info['cmdline'][-1].endswith('aw-systray-odoo.py')]) > 1


def notify(message, monitor=None):
    if IS_WINDOWS:
        if monitor:
            monitor.indicator.notify(message, title="Odoo Activity Watch")
            return
        try:
            from win10toast import ToastNotifier

            ToastNotifier().show_toast("Odoo Activity Watch", message, duration=3)
        except ImportError:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "Odoo Activity Watch", 0)
    elif IS_MACOS:
        # Posting from our own process makes macOS show the .app bundle icon;
        # osascript notifications always carry the Script Editor icon.
        center = None
        if getattr(sys, 'frozen', False):
            from Foundation import NSUserNotification, NSUserNotificationCenter
            center = NSUserNotificationCenter.defaultUserNotificationCenter()
        if center:
            notification = NSUserNotification.alloc().init()
            notification.setTitle_("Odoo Activity Watch")
            notification.setInformativeText_(message)
            center.deliverNotification_(notification)
        else:
            escaped = message.replace('\\', '\\\\').replace('"', '\\"')
            script = f'display notification "{escaped}" with title "Odoo Activity Watch"'
            subprocess.run(["osascript", "-e", script], check=False)
    else:
        subprocess.run(["notify-send", "Odoo Activity Watch", message], check=False)


def is_aw_accessible(url):
    """Return True if the Activity Watch HTTP API responds."""
    try:
        urllib.request.urlopen(f"{url}/api/0/info", timeout=2)
        return True
    except Exception:
        return False


def get_menu_items(monitor):
    return [
        {"label": "View Timeline", "action": monitor.open_ui, "default": True},
        {"is_separator": True},
        {
            "label": "Start Server",
            "action": monitor.start_server,
            "visible": "server_stopped",
        },
        {
            "label": "Restart Server",
            "action": monitor.restart_server,
            "visible": "server_running",
        },
        {
            "label": "Stop Server",
            "action": monitor.stop_server,
            "visible": "server_running",
        },
        {"is_separator": True},
        {
            "label": "Settings",
            "action": monitor.open_ui_settings,
            "visible": "server_running",
        },
        {"label": "Help", "action": monitor.about},
        {"label": "About ActivityWatch", "action": monitor.about_activitywatch},
        {"is_separator": True},
        {"label": "Quit", "action": monitor.on_quit},
    ]


class ActivityWatchMonitor:
    def __init__(self):
        self.procs = []
        self.url = "http://127.0.0.1:5600"
        icon, idle_icon = get_icon()
        self.icon = icon
        self.indicator = None
        self.idle_icon = idle_icon
        self.icon_path = self.idle_icon_path = None
        self.active_buttons = []
        self.idle_buttons = []
        self.is_server_running = False

    def get_server_icon(self):
        return self.icon if self.is_server_running else self.idle_icon

    def get_server_icon_path(self):
        return self.icon_path if self.is_server_running else self.idle_icon_path

    def check_extension(self):
        if USE_PYSTRAY:
            return
        result = subprocess.run(['gnome-extensions', 'list', '--enabled'], capture_output=True, text=True, check=False)
        if 'focused-window-dbus@flexagoon.com' not in result.stdout.split('\n'):
            subprocess.run(['gnome-extensions', 'enable', 'focused-window-dbus@flexagoon.com'], capture_output=True, text=True, check=False)

    def wait_for_extension(self, max_wait=60, interval=2):
        """Wait until the GNOME extension is active before launching the server.

        Called during auto-start where GNOME Shell may not have fully loaded
        the extension yet. Enables it if needed, then polls until ACTIVE.
        """
        if USE_PYSTRAY:
            return
        self.check_extension()
        extension_id = "focused-window-dbus@flexagoon.com"
        elapsed = 0
        while elapsed < max_wait:
            result = subprocess.run(
                ["gnome-extensions", "info", extension_id],
                capture_output=True,
                text=True,
                check=False,
            )
            if "State: ACTIVE" in result.stdout:
                return
            time.sleep(interval)
            elapsed += interval

    def save_icons(self):
        temp_dir = tempfile.gettempdir()
        icon_path = os.path.join(temp_dir, "my-aw-icon.png")
        self.icon.save(icon_path)
        idle_icon_path = os.path.join(temp_dir, "my-aw-icon-stop.png")
        self.idle_icon.save(idle_icon_path)
        self.icon_path = icon_path
        self.idle_icon_path = idle_icon_path

    def _launch_binaries(self, notify_errors=True):
        """Spawn AW binaries without touching the UI or stopping running processes."""
        self.check_extension()
        for binary in binaries:
            if not os.path.exists(binary):
                if notify_errors:
                    notify(f"Binary not found: {binary}", self)
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
                if notify_errors:
                    notify(f"{binary} not started", self)
                    notify(f"{b.args} <b>Not started</b>", self)
                return False
        return True

    def _stop_server(self):
        for p in self.procs:
            p.poll()
            if p.returncode is None:
                p.terminate()
        self.procs = []
        self.is_server_running = False

    def stop_server(self, widget=None):
        self._stop_server()
        if USE_PYSTRAY:
            self.indicator.icon = self.idle_icon
            self.indicator.title = "Server Stopped"
        else:
            self.indicator.set_icon_full(self.idle_icon_path, "Server Stopped")
            self.update_buttons_visibility()
        notify("Server Stopped", self)

    def open_ui(self, widget=None):
        webbrowser.open(f"{self.url}/#/timeline")

    def open_ui_settings(self, widget=None):
        webbrowser.open(f"{self.url}/#/settings")

    def about(self, widget=None):
        webbrowser.open("https://www.odoo.com/documentation/saas-19.1/applications/services/timesheets/timesheet_assistant.html")

    def about_activitywatch(self, widget=None):
        webbrowser.open("https://activitywatch.net")

    def _start_server(self):
        self._stop_server()
        is_launched = self._launch_binaries()
        self.is_server_running = True
        if is_launched:
            if USE_PYSTRAY:
                self.indicator.icon = self.icon
                self.indicator.title = "Server running"
            else:
                self.indicator.set_icon_full(self.icon_path, "Server stopped")
                self.update_buttons_visibility()
        return is_launched

    def start_server(self, widget=None):
        is_launched = self._start_server()
        if is_launched:
            notify("Server started", self)

    def restart_server(self, widget=None):
        is_launched = self._start_server()
        if is_launched:
            notify("Server restarted", self)

    def update_buttons_visibility(self):
        if not USE_PYSTRAY:
            for button in self.idle_buttons:
                button.set_visible(not self.is_server_running)
            for button in self.active_buttons:
                button.set_visible(self.is_server_running)

    def on_quit(self, widget=None):
        self.stop_server()
        if USE_PYSTRAY:
            if self.indicator:
                self.indicator.stop()
        else:
            Gtk.main_quit()


if USE_PYSTRAY:

    def generate_menu_items(monitor):
        menu_items = get_menu_items(monitor)
        pystray_items = []
        for item in menu_items:
            if item.get("is_separator"):
                pystray_items.append(pystray.Menu.SEPARATOR)
            else:
                if "visible" in item:
                    state = item.get("visible")
                    if (
                        state == "server_running" and not monitor.is_server_running
                    ) or (state == "server_stopped" and monitor.is_server_running):
                        continue
                menu_item = pystray.MenuItem(
                    item["label"],
                    item["action"],
                    default=item.get("default", False),
                )
                pystray_items.append(menu_item)
        return pystray_items

    def create_indicator(name, monitor, message):
        indicator = pystray.Icon(name, monitor.get_server_icon(), name)
        indicator.menu = pystray.Menu(lambda: generate_menu_items(monitor))
        monitor.indicator = indicator
        if message:
            notify(message, monitor)
        indicator.run()
        return indicator
else:

    def generate_menu_items(monitor):
        menu_items = get_menu_items(monitor)
        menu = Gtk.Menu()
        for item in menu_items:
            if item.get("is_separator"):
                menu.append(Gtk.SeparatorMenuItem())
            else:
                menu_item = Gtk.MenuItem(label=item["label"])
                menu_item.connect("activate", item["action"])
                menu.append(menu_item)
                if "visible" in item:
                    state = item.get("visible")
                    if state == "server_running":
                        monitor.active_buttons.append(menu_item)
                    elif state == "server_stopped":
                        monitor.idle_buttons.append(menu_item)
        return menu

    def create_indicator(name, monitor, message):
        monitor.save_icons()
        indicator = AppIndicator3.Indicator.new(
            name,
            monitor.get_server_icon_path(),
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        menu = generate_menu_items(monitor)
        menu.show_all()
        indicator.set_menu(menu)
        monitor.indicator = indicator
        monitor.update_buttons_visibility()
        if message:
            notify(message, monitor)
        Gtk.main()
        return indicator


if __name__ == "__main__":
    if systray_already_running():
        notify("Systray app is already running !")
        sys.exit(0)

    monitor = ActivityWatchMonitor()

    MAX_RETRIES = 3
    RETRY_DELAY = 5  # seconds to wait for the server to become reachable

    monitor.wait_for_extension()

    message = ""
    if is_aw_accessible(monitor.url):
        monitor.is_server_running = True
    else:
        for attempt in range(1, MAX_RETRIES + 1):
            # Kill the previous attempt's processes first, otherwise each retry
            # stacks another set of watchers (and permission prompts on macOS).
            monitor._stop_server()
            monitor._launch_binaries(notify_errors=False)
            time.sleep(RETRY_DELAY)
            if is_aw_accessible(monitor.url):
                monitor.is_server_running = True
                message = "Activity Watch started successfully"
                break
        else:
            message = f"Activity Watch could not be started after {MAX_RETRIES} attempts"

    indicator = create_indicator("Odoo ActivityWatch", monitor, message)
