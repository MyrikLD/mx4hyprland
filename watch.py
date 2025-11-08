import logging
import os
import argparse
from _socket import SO_REUSEADDR, SOL_SOCKET
from contextlib import contextmanager
from socket import AF_UNIX, SOCK_STREAM, socket
from typing import Iterator

from mx_master_4 import MXMaster4, DeviceDisconnectedError

XDG_RUNTIME_DIR = os.getenv("XDG_RUNTIME_DIR")
HYPRLAND_INSTANCE_SIGNATURE = os.getenv("HYPRLAND_INSTANCE_SIGNATURE")


@contextmanager
def hyprland_socket():
    with socket(AF_UNIX, SOCK_STREAM) as s:
        s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        s.connect(f"{XDG_RUNTIME_DIR}/hypr/{HYPRLAND_INSTANCE_SIGNATURE}/.socket2.sock")
        yield s


def hyprland_listener() -> Iterator[tuple[str, list[str]]]:
    with hyprland_socket() as s:
        while True:
            response = s.recv(1024).decode(errors="replace")
            packages = response.rstrip("\n").split("\n")
            for pkg in packages:
                cmd, args_ = pkg.split(">>", 1)
                args = args_.split(",")
                yield cmd, args


def main():
    parser = argparse.ArgumentParser(description="Hyprland active window watcher for MX Master 4 haptic feedback.")
    parser.add_argument('--debug', action='store_true', help="Enable debug logging.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    
    device = MXMaster4.find()
    if not device:
        logging.error("MX Master 4 not found! Exiting.")
        exit(1)

    try:
        while True:
            try:
                with device as dev:
                    last_window = None
                    for cmd, args in hyprland_listener():
                        logging.debug("%s -> %s", cmd, ",".join(args))
                        if cmd == "activewindowv2":
                            if args == last_window:
                                continue
                            dev.send_haptic_feedback(effect_id=2)
                            last_window = args
            except DeviceDisconnectedError:
                logging.warning("Device disconnected. Attempting to reconnect...")
                device = MXMaster4.find()
                if not device:
                    logging.error("Failed to find a new device. Exiting.")
                    break
                logging.info(f"Reconnected to device via {device.connection_type}.")
            except Exception as e:
                logging.error(f"An unexpected error occurred: {e}")
                break
    except KeyboardInterrupt:
        logging.info("Watcher stopped by user.")


if __name__ == "__main__":
    main()
