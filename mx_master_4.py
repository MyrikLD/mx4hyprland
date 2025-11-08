import logging
import os
import sys
from enum import IntEnum, StrEnum
from struct import pack, unpack

import hid
import glob
from time import sleep

LOGITECH_VID = 0x046D
MX_MASTER_4_BLUETOOTH_PID = 0xB042
MX_MASTER_4_BLUETOOTH_NAME = "MX Master 4"


class ConnectionType(StrEnum):
    BOLT = "bolt"
    BLUETOOTH = "bluetooth"


class ReportID(IntEnum):
    Short = 0x10  # 7 bytes
    Long = 0x11  # 20 bytes


class FunctionID(IntEnum):
    IRoot = 0x0000
    IFeatureSet = 0x0001
    IFeatureInfo = 0x0002

    Haptic = 0x0B4E


class DeviceDisconnectedError(Exception):
    """Custom exception for device disconnection."""
    pass


class MXMaster4:
    device = None
    connection_type = None
    device_path = None
    device_idx = None

    def __init__(self, connection_type: StrEnum, path: str | None = None, device_idx: int | None = None):
        self.connection_type = connection_type
        self.device_path = path
        self.device_idx = device_idx
        logging.info(f"Device found via %s", self.connection_type)

    @classmethod
    def find(cls, connection_type: StrEnum | None = None, device_path: str | None = None):
        if connection_type == ConnectionType.BOLT or connection_type is None:
            bolt_device = cls._find_bolt_device()
            if bolt_device:
                return bolt_device

        if connection_type == ConnectionType.BLUETOOTH or connection_type is None:
            path = device_path or cls._find_bluetooth_path()
            if path:
                return cls(connection_type=ConnectionType.BLUETOOTH, path=path)
        
        # This part of the original code is unreachable if connection_type is None,
        # but kept for consistency if a specific type is requested and not found.
        if connection_type:
             logging.error(f"MX Master 4 with connection type '{connection_type}' not found!")
        return None

    @classmethod
    def _find_bolt_device(cls):
        devices = hid.enumerate(LOGITECH_VID)
        for device in devices:
            if device["usage_page"] == 65280:  # HID++
                path = device["path"].decode("utf-8")
                logging.debug(f"Found Bolt device: %s", device["product_string"])
                logging.debug(f"	Path: %s", path)
                logging.debug(f"	Interface: %s", device.get("interface_number"))
                return cls(connection_type=ConnectionType.BOLT, path=path, device_idx=device["interface_number"])
        return None

    @classmethod
    def _find_bluetooth_path(cls):
        hidraw_path = "/sys/class/hidraw"
        try:
            for d in os.listdir(hidraw_path):
                device_symlink = os.path.join(hidraw_path, d, 'device')
                if not os.path.islink(device_symlink):
                    continue

                actual_device_path = os.path.realpath(device_symlink)
                uevent_path = os.path.join(actual_device_path, "uevent")
                name_path_glob = os.path.join(actual_device_path, "input", "input*", "name")
                name_paths = glob.glob(name_path_glob)

                if not (os.path.exists(uevent_path) and name_paths):
                    continue

                name_path = name_paths[0]
                with open(name_path, 'r') as f:
                    name = f.read().strip()

                if MX_MASTER_4_BLUETOOTH_NAME in name:
                    with open(uevent_path, 'r') as f:
                        uevent = f.read().upper()
                    
                    vid_hex = f"{LOGITECH_VID:04X}"
                    pid_hex = f"{MX_MASTER_4_BLUETOOTH_PID:04X}"
                    unpadded_id = f"HID_ID=0005:{vid_hex}:{pid_hex}"
                    padded_id = f"HID_ID=0005:0000{vid_hex}:0000{pid_hex}"

                    if unpadded_id in uevent or padded_id in uevent:
                        dev_node = os.path.join("/dev", d)
                        logging.info(f"SUCCESS: Found Bluetooth device: {name} at {dev_node}")
                        return dev_node
        except (OSError, IOError) as e:
            logging.error(f"Error scanning for Bluetooth devices: {e}")
        return None

    def __enter__(self):
        if self.connection_type == ConnectionType.BOLT:
            self.device = hid.Device(path=self.device_path.encode())
        elif self.connection_type == ConnectionType.BLUETOOTH:
            try:
                self.device = open(self.device_path, "wb")
            except PermissionError:
                logging.error(f"Permission denied for {self.device_path}. Run with 'sudo' or check udev rules.")
                raise
            except Exception as e:
                logging.error(f"Failed to open Bluetooth device: {e}")
                raise
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.device:
            try:
                self.device.close()
            except OSError as e:
                # Ignore "No such device" error on close, as it's expected if disconnected
                if e.errno != 19:
                    raise

    def _write_bluetooth(self, data: bytes):
        if not self.device or self.device.closed:
            raise ConnectionError("Bluetooth device is not open.")
        try:
            logging.debug(f"Writing to Bluetooth: {' '.join(f'{b:02x}' for b in data)}")
            self.device.write(data)
            self.device.flush()
        except OSError as e:
            if e.errno == 19:  # No such device
                raise DeviceDisconnectedError from e
            else:
                raise

    def send_haptic_feedback(self, effect_id: int = 1):
        if self.connection_type == ConnectionType.BOLT:
            if not (0 <= effect_id <= 15):
                raise ValueError("Bolt effect_id must be between 0 and 15.")
            self._send_bolt_hidpp(FunctionID.Haptic, effect_id)
        
        elif self.connection_type == ConnectionType.BLUETOOTH:
            if not (0 <= effect_id <= 15):
                raise ValueError("Bluetooth effect_id must be between 0 and 15.")
            
            payload = [0xFF, 0x0B, 0x4E, effect_id]
            padding = [0] * (19 - len(payload))
            packet = bytes([ReportID.Long] + payload + padding)
            self._write_bluetooth(packet)

    def _send_bolt_hidpp(
        self,
        feature_idx: FunctionID,
        *args: int,
    ) -> tuple[int, bytes]:
        if self.connection_type != ConnectionType.BOLT:
            raise NotImplementedError("_send_bolt_hidpp is only supported for Bolt connections.")
        
        if not self.device or not isinstance(self.device, hid.Device):
             raise ConnectionError("Bolt device is not open.")

        data = bytes(args)
        if len(data) < 3:
            data += bytes([0]) * (3 - len(data))

        report_id = ReportID.Short if len(data) == 3 else ReportID.Long
        packet = pack(b">BBH%ds" % len(data), report_id, self.device_idx, feature_idx, data)
        
        try:
            logging.debug(f"Writing to Bolt (HID++): {' '.join(f'{b:02x}' for b in packet)}")
            self.device.write(packet)
            response = self.device.read(20)
        except hid.HIDException as e:
            raise DeviceDisconnectedError from e
        
        (r_report_id, r_device_idx, r_f_idx) = unpack(b">BBH", response[:4])
        if r_device_idx != self.device_idx:
            return None, None
        return r_f_idx, response[4:]


def demo():
    import argparse

    parser = argparse.ArgumentParser(description="Demo script for MX Master 4 haptic effects.")
    parser.add_argument(
        '--connection', 
        type=str, 
        choices=['bolt', 'bluetooth'], 
        default='bolt',
        help="The connection type to use. Defaults to 'bolt', then tries 'bluetooth' if not found."
    )
    parser.add_argument('--path', type=str, default=None, help="Manually specify the device path (optional, for Bluetooth).")
    parser.add_argument('--debug', action='store_true', help="Enable debug logging.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    mx_master_4 = MXMaster4.find(connection_type=args.connection, device_path=args.path)

    if not mx_master_4:
        sys.exit(1)

    with mx_master_4 as dev:
        num_effects = 16 # Both Bolt and Bluetooth will iterate 0-15
        logging.info(f"--- Demonstrating {num_effects} haptic effects for {dev.connection_type.upper()} connection ---")
        
        for i in range(1, num_effects):
            logging.info(f"Playing effect {i}...")
            try:
                dev.send_haptic_feedback(effect_id=i)
                sleep(2)
            except Exception as e:
                logging.error(f"Failed to play effect {i}: {e}")
                break
        
        dev.send_haptic_feedback(effect_id=0) # Send effect 0 to turn off haptics
        logging.info("--- Demo finished ---")


if __name__ == "__main__":
    demo()
