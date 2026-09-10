"""Windows notification-area monitor for the local SignalDesk service."""

from __future__ import annotations

import socket
import subprocess
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Literal

import pystray
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_NAME = "SignalDeskServer"
LOCAL_URL = "http://127.0.0.1:8000"
ServiceState = Literal["RUNNING", "STOPPED", "PENDING", "MISSING", "UNKNOWN"]


def service_state() -> ServiceState:
    result = subprocess.run(
        ["sc.exe", "query", SERVICE_NAME],
        capture_output=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
        text=True,
    )
    if result.returncode == 1060:
        return "MISSING"
    if result.returncode != 0:
        return "UNKNOWN"
    if "RUNNING" in result.stdout:
        return "RUNNING"
    if "STOPPED" in result.stdout:
        return "STOPPED"
    return "PENDING"


def status_icon(running: bool) -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    drawing = ImageDraw.Draw(image)
    drawing.ellipse((8, 8, 56, 56), fill="#35a980" if running else "#d95d52")
    drawing.ellipse((20, 20, 44, 44), fill="#ffffff")
    return image


def lan_url() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("8.8.8.8", 80))
            host = connection.getsockname()[0]
    except OSError:
        host = socket.gethostbyname(socket.gethostname())
    return f"http://{host}:8000"


def copy_lan_url(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    import tkinter
    root = tkinter.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(lan_url())
    root.update()
    root.destroy()
    icon.notify(f"Copied {lan_url()}", "SignalDesk")


def refresh(icon: pystray.Icon) -> None:
    state = service_state()
    icon.icon = status_icon(state == "RUNNING")
    icon.title = f"SignalDesk service: {state.lower()}"
    icon.update_menu()


def run_monitor(icon: pystray.Icon) -> None:
    while icon.visible:
        refresh(icon)
        time.sleep(15)


def change_service_state(icon: pystray.Icon, command: str, action: str) -> None:
    result = subprocess.run(
        ["sc.exe", command, SERVICE_NAME],
        capture_output=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
        text=True,
    )
    if result.returncode == 0:
        icon.notify(f"Service {action} requested.", "SignalDesk")
    else:
        detail = (result.stderr or result.stdout).strip()
        icon.notify(f"Could not {action} service: {detail or 'Windows rejected the request.'}", "SignalDesk")
    refresh(icon)


def start_service(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    change_service_state(icon, "start", "start")


def stop_service(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    change_service_state(icon, "stop", "stop")


def restart_service(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    change_service_state(icon, "stop", "stop")
    time.sleep(1)
    change_service_state(icon, "start", "start")


def open_logs(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    subprocess.Popen(["explorer.exe", str(PROJECT_ROOT / "logs")])


def quit_monitor(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    icon.stop()


def main() -> None:
    initial_state = service_state()
    icon = pystray.Icon("SignalDesk", status_icon(initial_state == "RUNNING"), "SignalDesk")
    icon.menu = pystray.Menu(
        pystray.MenuItem("Open SignalDesk", lambda _icon, _item: webbrowser.open(LOCAL_URL)),
        pystray.MenuItem("Start service", start_service, enabled=lambda _item: service_state() == "STOPPED"),
        pystray.MenuItem("Stop service", stop_service, enabled=lambda _item: service_state() == "RUNNING"),
        pystray.MenuItem("Restart service", restart_service, enabled=lambda _item: service_state() == "RUNNING"),
        pystray.MenuItem("View logs", open_logs),
        pystray.MenuItem("Copy LAN URL", copy_lan_url),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", quit_monitor),
    )
    threading.Thread(target=run_monitor, args=(icon,), daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()