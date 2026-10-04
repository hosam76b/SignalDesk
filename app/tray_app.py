"""Windows notification-area monitor for the local SignalDesk service."""

from __future__ import annotations

import ctypes
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
ACTION_TIMEOUT_SECONDS = 30
service_action_in_progress = threading.Event()


def is_access_denied_error(output: str) -> bool:
    text = (output or "").lower()
    return "access is denied" in text or "failed 5" in text or "error 5" in text


def request_admin_for_service_action(action: str) -> bool:
    if not hasattr(ctypes, "windll") or not hasattr(ctypes.windll, "shell32"):
        return False

    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            "cmd.exe",
            f"/c sc.exe {action} {SERVICE_NAME}",
            None,
            1,
        )
        return result > 32
    except Exception:
        return False


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
    drawing.rounded_rectangle((3, 3, 61, 61), radius=12, fill="#0f172a", outline="#334155", width=2)
    drawing.polygon(((32, 7), (57, 32), (32, 57), (7, 32)), outline="#38bdf8", width=4)
    drawing.polygon(((32, 16), (48, 32), (32, 48), (16, 32)), outline="#38bdf8", width=2)
    drawing.ellipse((24, 24, 40, 40), fill="#e11d48")
    drawing.ellipse((29, 29, 35, 35), fill="#ffffff")
    badge_color = "#16a36f" if running else "#dc4b44"
    drawing.ellipse((43, 43, 61, 61), fill="#ffffff")
    drawing.ellipse((47, 47, 57, 57), fill=badge_color)
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
    icon.title = f"SignalDesk service: {state.title()}"
    icon.update_menu()


def run_monitor(icon: pystray.Icon) -> None:
    icon.visible = True
    while icon.visible:
        refresh(icon)
        time.sleep(3)


def wait_for_service_state(expected_state: ServiceState) -> ServiceState:
    deadline = time.monotonic() + ACTION_TIMEOUT_SECONDS
    state = service_state()
    while state != expected_state and time.monotonic() < deadline:
        time.sleep(1)
        state = service_state()
    return state


def request_service_state(icon: pystray.Icon, command: str, action: str, expected_state: ServiceState) -> bool:
    result = subprocess.run(
        ["sc.exe", command, SERVICE_NAME],
        capture_output=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
        text=True,
    )
    if result.returncode == 0:
        state = wait_for_service_state(expected_state)
        refresh(icon)
        if state == expected_state:
            icon.notify(f"Service is now {expected_state.lower()}.", "SignalDesk")
            return True
        icon.notify(f"Service did not {action} within {ACTION_TIMEOUT_SECONDS} seconds (current state: {state.lower()}).", "SignalDesk")
        return False

    detail = (result.stderr or result.stdout).strip()
    if is_access_denied_error(detail):
        if request_admin_for_service_action(command):
            icon.notify("Administrator permission requested. Waiting for Windows to update the service.", "SignalDesk")
            state = wait_for_service_state(expected_state)
            refresh(icon)
            if state == expected_state:
                icon.notify(f"Service is now {expected_state.lower()}.", "SignalDesk")
                return True
            icon.notify(f"Service did not {action} within {ACTION_TIMEOUT_SECONDS} seconds (current state: {state.lower()}).", "SignalDesk")
        else:
            icon.notify(
                f"Could not {action} service: Windows denied access. Run the app as administrator.",
                "SignalDesk",
            )
    else:
        icon.notify(f"Could not {action} service: {detail or 'Windows rejected the request.'}", "SignalDesk")
    refresh(icon)
    return False


def run_service_action(icon: pystray.Icon, action: str) -> None:
    if service_action_in_progress.is_set():
        return

    service_action_in_progress.set()
    refresh(icon)
    try:
        if action == "start":
            request_service_state(icon, "start", "start", "RUNNING")
        elif action == "stop":
            request_service_state(icon, "stop", "stop", "STOPPED")
        else:
            if request_service_state(icon, "stop", "stop", "STOPPED"):
                request_service_state(icon, "start", "start", "RUNNING")
    finally:
        service_action_in_progress.clear()
        refresh(icon)


def start_service(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    threading.Thread(target=run_service_action, args=(icon, "start"), daemon=True).start()


def stop_service(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    threading.Thread(target=run_service_action, args=(icon, "stop"), daemon=True).start()


def restart_service(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    threading.Thread(target=run_service_action, args=(icon, "restart"), daemon=True).start()


def action_available(required_state: ServiceState) -> bool:
    return not service_action_in_progress.is_set() and service_state() == required_state


def open_logs(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    subprocess.Popen(["explorer.exe", str(PROJECT_ROOT / "logs")])


def quit_monitor(icon: pystray.Icon, _item: pystray.MenuItem) -> None:
    icon.stop()


def main() -> None:
    initial_state = service_state()
    icon = pystray.Icon("SignalDesk", status_icon(initial_state == "RUNNING"), "SignalDesk")
    icon.menu = pystray.Menu(
        pystray.MenuItem(lambda _item: f"Service status: {service_state().title()}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open SignalDesk", lambda _icon, _item: webbrowser.open(LOCAL_URL)),
        pystray.MenuItem("Start service", start_service, enabled=lambda _item: action_available("STOPPED")),
        pystray.MenuItem("Stop service", stop_service, enabled=lambda _item: action_available("RUNNING")),
        pystray.MenuItem("Restart service", restart_service, enabled=lambda _item: action_available("RUNNING")),
        pystray.MenuItem("View logs", open_logs),
        pystray.MenuItem("Copy LAN URL", copy_lan_url),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", quit_monitor),
    )
    icon.run(setup=run_monitor)


if __name__ == "__main__":
    main()