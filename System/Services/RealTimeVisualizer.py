from __future__ import annotations

import os
import sys
import time
import json
import copy
import queue
import base64
import select
import socket
import threading

from loguru import logger

from PyQt6.QtCore import (
    QTimer,
    QObject,
    QProcess,
    pyqtSignal
)

from System.Common import Utils

from System.Services  import Player
from System.Interface import Timing

RECEIVER_TCP_PORT = 7777
RECEIVER_UDP_PORT = 7778

if sys.platform == "win32":
    ADB_PATH = Utils.get_resource_path("System/ADB/adb.exe")

elif sys.platform == "darwin":
    ADB_PATH = Utils.get_resource_path("System/ADB/adb-macos")

else:
    ADB_PATH = Utils.get_resource_path("System/ADB/adb-linux")

# Enrichment

def create_enriched_glyph_data(
        glyph_identifier: str,
        glyph_content:    dict,
        composition:      object
    ) -> dict:

    item_copy: dict = glyph_content.copy()

    if "effect" in glyph_content and composition is not None:
        cached_effects_map = composition.cached_effects

        if int(glyph_identifier) in cached_effects_map:
            item_copy["effect_to_glyphs"] = cached_effects_map[int(glyph_identifier)]

    return item_copy

# Glyph Syncer

class GlyphSyncer(QObject):
    ping_updated       = pyqtSignal(float)
    high_ping_detected = pyqtSignal(float)
    error_occurred     = pyqtSignal(str, str)
    device_changed     = pyqtSignal(list)
    status_changed     = pyqtSignal(str, str)

    def __init__(
            self,
            parent: QObject = None
        ) -> None:

        super().__init__(parent)

        self.initialized:          bool                    = True
        self.composition:          object                  = None
        self.connected_model:      str | None              = None
        self.client_socket:        socket.socket | None    = None
        self.last_ping_ms:         float                   = 0.0

        self.devices:              list[str]               = []
        self.blocked_devices:      list[str]               = []
        self.processes:            list[QProcess]          = []
        self.last_synced:          dict                    = {}

        self.connection_mode:      str | None              = None
        self.active_ip_address:    str | None              = None
        self.is_connecting:        bool                    = False
        self.is_sender_active:     bool                    = False
        self.has_warned_high_ping: bool                    = False

        self.send_queue:           queue.Queue             = queue.Queue()
        self.sender_thread:        threading.Thread | None = None

        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp_socket.setblocking(False)

        self.scan_timer = Timing.Timer(
            interval = 1500,
            callback = self.scan_devices,
            parent   = self
        )

        self.heartbeat_timer = Timing.Timer(
            interval = 1000,
            callback = self.send_heartbeat_ping,
            parent   = self
        )

    def set_composition(self, composition: object) -> None:
        self.composition = composition

    def start_scanning_loop(self) -> None:
        if self.connection_mode == "cable" and self.client_socket is not None:
            return

        if self.scan_timer.isActive():
            return

        self.run_command_async(["start-server"])
        self.scan_timer.start()

    def stop_scanning_loop(self) -> None:
        if not self.scan_timer.isActive():
            return

        self.scan_timer.stop()

    def disconnect_socket(self) -> None:
        self.heartbeat_timer.stop()
        self.is_sender_active     = False
        self.has_warned_high_ping = False

        while not self.send_queue.empty():
            try:
                self.send_queue.get_nowait()

            except queue.Empty:
                break

        if self.client_socket is not None:
            try:
                self.client_socket.shutdown(socket.SHUT_RDWR)

            except Exception:
                pass

            try:
                self.client_socket.close()

            except Exception:
                pass

            self.client_socket = None

        self.connection_mode   = None
        self.active_ip_address = None
        self.is_connecting     = False

    # Process

    def run_command_async(
            self,
            arguments:   list[str],
            on_finished: object = None,
            on_error:    object = None
        ) -> QProcess:

        if arguments and arguments[0] != ADB_PATH:
            arguments = [ADB_PATH] + arguments

        process: QProcess = QProcess(self)
        self.processes.append(process)

        def cleanup() -> None:
            if process in self.processes:
                self.processes.remove(process)

            process.deleteLater()

        def finished(
                exit_code:   int,
                exit_status: QProcess.ExitStatus
            ) -> None:

            standard_output: str = bytes(process.readAllStandardOutput()).decode(errors = "ignore")
            standard_error:  str = bytes(process.readAllStandardError()).decode(errors = "ignore")

            if exit_code != 0:
                if on_error:
                    on_error(process, exit_code, standard_error)

                cleanup()

                return

            if on_finished:
                on_finished(process, standard_output, standard_error)

            cleanup()

        process.finished.connect(finished)
        process.start(arguments[0], arguments[1:])

        return process

    # Discovery

    def scan_devices(self) -> None:
        if self.connection_mode == "cable" and self.client_socket is not None:
            return

        if self.is_connecting:
            return

        self.run_command_async(
            arguments   = ["devices"],
            on_finished = self.on_devices_listed
        )

    def send_wireless_discovery_probe(self) -> None:
        probe_bytes: bytes = json.dumps({"cmd": "CASSETTE_DISCOVERY_PROBE"}).encode()

        try:
            self.udp_socket.sendto(probe_bytes, ("255.255.255.255", RECEIVER_UDP_PORT))

        except Exception:
            try:
                self.udp_socket.sendto(probe_bytes, ("<broadcast>", RECEIVER_UDP_PORT))

            except Exception:
                pass

    def check_wireless_discovery_responses(self) -> None:
        while True:
            try:
                readable, writable, exceptional = select.select([self.udp_socket], [], [], 0.0)

                if not readable:
                    break

                received_data, address_pair = self.udp_socket.recvfrom(2048)
                sender_ip_address:   str    = address_pair[0]
                response_dictionary: dict   = json.loads(received_data.decode("utf-8", errors = "ignore"))

                if response_dictionary.get("service") != "cassette_receiver":
                    continue

                if self.connection_mode == "cable" or self.client_socket is not None or self.is_connecting:
                    break

                logger.info(f"Discovered Receiver via Wi-Fi at {sender_ip_address}")
                self.connect_asynchronous(sender_ip_address, RECEIVER_TCP_PORT, "wireless")

                break

            except Exception:
                break

    def on_devices_listed(
            self,
            process:         QProcess,
            standard_output: str,
            standard_error:  str
        ) -> None:

        lines:    list[str] = standard_output.strip().splitlines()
        new_list: list[str] = [line.split()[0] for line in lines[1:] if "device" in line]

        available_devices = [device for device in new_list if device not in self.blocked_devices]

        if available_devices:
            target_device = available_devices[0]

            if self.connection_mode == "wireless":
                logger.info(f"Cable device available ({target_device}). Disconnecting wireless and switching to cable.")
                self.disconnect_socket()
                self.initialize_adb_device(target_device)

                return

            if self.client_socket is None and not self.is_connecting:
                self.devices = new_list
                self.device_changed.emit(new_list)
                self.initialize_adb_device(target_device)

                return

        self.devices = new_list
        self.device_changed.emit(new_list)

        if self.client_socket is not None or self.is_connecting:
            return

        self.send_wireless_discovery_probe()
        self.check_wireless_discovery_responses()

    # Device Initialization

    def initialize_adb_device(self, device_identifier: str) -> None:
        if self.connection_mode == "cable" and self.client_socket is not None:
            return

        if self.is_connecting:
            return

        def check_package(
                sub_process:     QProcess,
                standard_output: str,
                standard_error:  str
            ) -> None:

            is_installed: bool = standard_output.strip().startswith("package:")

            if not is_installed:
                if device_identifier not in self.blocked_devices:
                    self.blocked_devices.append(device_identifier)

                return

            command_sequence: list = [
                (["-s", device_identifier, "forward", f"tcp:{RECEIVER_TCP_PORT}", f"tcp:{RECEIVER_TCP_PORT}"], None),
                (["-s", device_identifier, "shell", "dumpsys", "deviceidle", "whitelist", "+com.glyph.receiver"], None),
                (["-s", device_identifier, "shell", "am", "start", "-n", "com.glyph.receiver/.MainActivity"], None),
            ]

            def on_cable_setup_completed() -> None:
                if self.connection_mode == "cable" and self.client_socket is not None:
                    return

                if self.is_connecting:
                    return

                QTimer.singleShot(
                    800,
                    lambda: self.connect_asynchronous("127.0.0.1", RECEIVER_TCP_PORT, "cable")
                )

            self.run_sequence(
                command_list = command_sequence,
                on_done      = on_cable_setup_completed
            )

        self.run_command_async(
            arguments   = ["-s", device_identifier, "shell", "pm", "path", "com.glyph.receiver"],
            on_finished = check_package
        )

    def run_sequence(
            self,
            command_list: list,
            on_done:      object = None
        ) -> None:

        if not command_list:
            if on_done:
                on_done()

            return

        arguments, callback = command_list[0]

        def step_finished(
                sub_process:     QProcess,
                standard_output: str,
                standard_error:  str
            ) -> None:

            if callback:
                callback(sub_process, standard_output, standard_error)

            self.run_sequence(command_list[1:], on_done = on_done)

        self.run_command_async(
            arguments   = arguments,
            on_finished = step_finished,
            on_error    = lambda process, code, error: step_finished(process, "", error)
        )

    # Connection

    def connect_asynchronous(
            self,
            host_address: str,
            port_number:  int,
            network_mode: str
        ) -> None:

        if network_mode == "cable" and self.connection_mode == "wireless":
            self.disconnect_socket()

        elif self.client_socket is not None:
            return

        if self.is_connecting:
            return

        self.is_connecting = True

        def connection_worker() -> None:
            try:
                created_socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

                created_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                created_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

                try:
                    created_socket.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 0x10)

                except Exception:
                    pass

                created_socket.settimeout(3.0)
                created_socket.connect((host_address, port_number))
                created_socket.settimeout(None)

                self.client_socket        = created_socket
                self.connection_mode      = network_mode
                self.active_ip_address    = host_address
                self.is_connecting        = False
                self.is_sender_active     = True
                self.has_warned_high_ping = False

                self.sender_thread = threading.Thread(
                    target = self.socket_sender_thread,
                    args   = (created_socket,),
                    daemon = True
                )
                self.sender_thread.start()

                if network_mode == "cable":
                    QTimer.singleShot(0, self.stop_scanning_loop)

                QTimer.singleShot(0, self.heartbeat_timer.start)

                logger.success(f"Connected to Receiver via {network_mode.upper()} [{host_address}:{port_number}]")
                self.status_changed.emit("connected", network_mode)

                threading.Thread(
                    target = self.socket_monitor_thread,
                    args   = (created_socket,),
                    daemon = True
                ).start()

                if self.composition is not None:
                    self.full_load(self.composition.all_glyphs())

                    current_speed = Player.player.speed

                    self.set_speed(current_speed)

                    if Player.player.is_playing:
                        current_position_ms = max(0, int(Player.player.get_position()))
                        self.play(current_position_ms)

            except Exception as exception:
                self.is_connecting = False
                logger.debug(f"Connection attempt to {host_address}:{port_number} failed: {exception}")

        threading.Thread(target = connection_worker, daemon = True).start()

    # Heartbeat and Ping

    def send_heartbeat_ping(self) -> None:
        if self.client_socket is None:
            return

        self.send_payload(
            {
                "action":    "ping",
                "timestamp": time.time()
            }
        )

    def handle_incoming_message(self, message_text: str) -> None:
        try:
            payload = json.loads(message_text)

        except Exception:
            return

        action = payload.get("action")

        if action == "pong":
            send_timestamp = payload.get("timestamp", 0.0)

            if send_timestamp > 0.0:
                latency_ms        = (time.time() - send_timestamp) * 1000.0
                self.last_ping_ms = latency_ms

                self.ping_updated.emit(latency_ms)

                if latency_ms > 120.0 and not self.has_warned_high_ping:
                    self.has_warned_high_ping = True
                    self.high_ping_detected.emit(latency_ms)

                    Player.ui_player.play_sound("Alerts/HighPing")

    # Socket Worker

    def socket_sender_thread(self, target_socket: socket.socket) -> None:
        while self.is_sender_active:
            try:
                payload_dictionary: dict = self.send_queue.get(timeout = 0.5)

            except queue.Empty:
                continue

            try:
                encoded_bytes: bytes = json.dumps(payload_dictionary, separators = (',', ':')).encode() + b"\n"
                target_socket.sendall(encoded_bytes)

            except Exception as error:
                logger.error(f"Failed to send payload: {error}")
                QTimer.singleShot(0, self.handle_disconnection)

                break

    def socket_monitor_thread(self, target_socket: socket.socket) -> None:
        target_socket.settimeout(10.0)
        accumulated_chunks = ""

        while True:
            try:
                received_bytes = target_socket.recv(4096)

                if not received_bytes:
                    break

                accumulated_chunks += received_bytes.decode("utf-8", errors = "ignore")

                while "\n" in accumulated_chunks:
                    line, accumulated_chunks = accumulated_chunks.split("\n", 1)
                    stripped_line            = line.strip()

                    if not stripped_line:
                        continue

                    self.handle_incoming_message(stripped_line)

            except Exception:
                break

        if self.client_socket == target_socket:
            QTimer.singleShot(0, self.handle_disconnection)

    def handle_disconnection(self) -> None:
        if self.client_socket is None and self.connection_mode is None:
            return

        logger.warning(f"Connection lost ({self.connection_mode})")

        self.disconnect_socket()
        self.status_changed.emit("disconnected", "")
        self.start_scanning_loop()

    # Payload Dispatch

    def send_payload(self, payload_dictionary: dict) -> None:
        if self.client_socket is None:
            return

        self.send_queue.put(payload_dictionary)

    # Ringtone Transfer

    def push_ringtone(self, file_path: str) -> None:
        if not os.path.exists(file_path):
            return

        file_name             = os.path.basename(file_path)
        destination_directory = "/sdcard/Ringtones/Compositions"

        for device_identifier in self.devices:
            destination_path = f"{destination_directory}/{file_name}"

            make_directory_command = [
                ADB_PATH,
                "-s",
                device_identifier,
                "shell",
                "mkdir",
                "-p",
                destination_directory
            ]

            Utils.run_hidden(make_directory_command)

            push_command = [
                ADB_PATH,
                "-s",
                device_identifier,
                "push",
                file_path,
                destination_path
            ]

            Utils.run_hidden(push_command)

            scan_command = [
                ADB_PATH,
                "-s",
                device_identifier,
                "shell",
                "am",
                "broadcast",
                "-a",
                "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                "-d",
                f"file://{destination_path}"
            ]

            Utils.run_hidden(scan_command)

        if self.client_socket is not None:
            try:
                with open(file_path, "rb") as file_handle:
                    encoded_content = base64.b64encode(file_handle.read()).decode("ascii")

                self.send_payload(
                    {
                        "action":  "save_ringtone",
                        "name":    file_name,
                        "content": encoded_content
                    }
                )

            except Exception as exception:
                logger.error(f"Failed to send ringtone over socket: {exception}")

    # Synchronization

    def sync(self, current_glyphs: dict) -> None:
        if current_glyphs is None:
            current_glyphs = {}

        current_data:        dict      = {str(identifier): glyph_data for identifier, glyph_data in current_glyphs.items()}
        deleted_identifiers: list[str] = list(set(self.last_synced) - set(current_data))

        def is_glyph_changed(
                old_glyph: dict,
                new_glyph: dict
            ) -> bool:

            if old_glyph["track"] != new_glyph["track"]:
                return True

            if old_glyph["start"] != new_glyph["start"]:
                return True

            if old_glyph["duration"] != new_glyph["duration"]:
                return True

            if ("brightness" in old_glyph) != ("brightness" in new_glyph):
                return True

            if "brightness" in old_glyph and old_glyph["brightness"] != new_glyph["brightness"]:
                return True

            if ("keyframes" in old_glyph) != ("keyframes" in new_glyph):
                return True

            if "keyframes" in old_glyph and old_glyph["keyframes"] != new_glyph["keyframes"]:
                return True

            if ("effect" in old_glyph) != ("effect" in new_glyph):
                return True

            if "effect" in old_glyph and old_glyph["effect"] != new_glyph["effect"]:
                return True

            if ("segments" in old_glyph) != ("segments" in new_glyph):
                return True

            if "segments" in old_glyph and old_glyph["segments"] != new_glyph["segments"]:
                return True

            return False

        changed_glyphs: dict = {}

        for glyph_identifier, glyph_content in current_data.items():
            if glyph_identifier not in self.last_synced:
                changed_glyphs[glyph_identifier] = glyph_content

                continue

            previous_glyph: dict = self.last_synced[glyph_identifier]

            if is_glyph_changed(previous_glyph, glyph_content):
                changed_glyphs[glyph_identifier] = glyph_content

        if deleted_identifiers:
            self.send_payload({"action": "delete", "ids": deleted_identifiers})

        if changed_glyphs:
            enriched_dictionary: dict = {}

            for glyph_identifier_key, glyph_item in changed_glyphs.items():
                enriched_dictionary[glyph_identifier_key] = create_enriched_glyph_data(
                    glyph_identifier = glyph_identifier_key,
                    glyph_content    = glyph_item,
                    composition      = self.composition
                )

            self.send_payload({"action": "update", "glyphs": enriched_dictionary})

        self.last_synced = copy.deepcopy(current_data)

    def full_load(self, glyphs_dictionary: dict) -> None:
        if glyphs_dictionary is None:
            glyphs_dictionary = {}

        enriched_list: list = []

        for glyph_identifier_key, glyph_item in glyphs_dictionary.items():
            item_copy: dict = create_enriched_glyph_data(
                glyph_identifier = str(glyph_identifier_key),
                glyph_content    = glyph_item,
                composition      = self.composition
            )

            item_copy["id"] = glyph_identifier_key

            enriched_list.append(item_copy)

        self.send_payload({"action": "load", "glyphs": enriched_list})
        self.last_synced = copy.deepcopy({str(key): value for key, value in glyphs_dictionary.items()})

        current_speed = Player.player.speed
        self.set_speed(current_speed)

    # Playback Control

    def play(self, milliseconds: int) -> None:
        self.send_payload({"action": "play", "from_ms": milliseconds})

    def stop(self) -> None:
        self.send_payload({"action": "stop"})

    def set_speed(self, speed_factor: float) -> None:
        self.send_payload({"action": "set_speed", "value": round(float(speed_factor), 3)})

    def pulse_track(self, track_identifier: str) -> None:
        self.send_payload({"action": "pulse", "track": track_identifier})

    def exit_app(self) -> None:
        self.send_payload({"action": "stop_app"})
        self.handle_disconnection()
        self.stop_scanning_loop()

    # Cleanup

    def cleanup(self) -> None:
        self.heartbeat_timer.stop()
        self.handle_disconnection()
        self.stop_scanning_loop()
        self.set_composition(None)

rt_visualizer: GlyphSyncer = GlyphSyncer()