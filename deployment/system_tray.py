"""Windows notification-area monitor for the local SignalDesk service."""

from __future__ import annotations

import socket
import subprocess
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_NAME = "SignalDeskServer"
LOCAL_URL = "http://127.0.0.1:8000"


def service_is_healthy() -> bool:
    try:
        with urllib.request.urlopen(f"{LOCAL_URL}/health", timeout=3) as response:
            return response.status == 200
    except OSError:
        return False


def status_icon(healthy: bool) -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    drawing = ImageDraw.Draw(image)
    drawing.ellipse((8, 8, 56, 56), fill="#35a980" if healthy else "#d95d52")
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
    healthy = service_is_healthy()
    icon.icon = status_icon(healthy)
    icon.title = f"SignalDesk: {'healthy' if healthy else 'service unavailable'}"


def run_monitor(icon: pystray.Icon) -> None:
    while icon.visible:
        refresh(icon)
        time.sleep(15)


def restart_service(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    subprocess.run(["sc.exe", "stop", SERVICE_NAME], check=False, creationflags=subprocess.CREATE_NO_WINDOW)
    subprocess.run(["sc.exe", "start", SERVICE_NAME], check=False, creationflags=subprocess.CREATE_NO_WINDOW)


def open_logs(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    subprocess.Popen(["explorer.exe", str(PROJECT_ROOT / "logs")])


def quit_monitor(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    icon.stop()


def main() -> None:
    icon = pystray.Icon("SignalDesk", status_icon(service_is_healthy()), "SignalDesk")
    icon.menu = pystray.Menu(
        pystray.MenuItem("Open SignalDesk", lambda _icon, _item: webbrowser.open(LOCAL_URL)),
        pystray.MenuItem("Restart service", restart_service),
        pystray.MenuItem("View logs", open_logs),
        pystray.MenuItem("Copy LAN URL", copy_lan_url),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", quit_monitor),
    )
    threading.Thread(target=run_monitor, args=(icon,), daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()