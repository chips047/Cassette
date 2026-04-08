import sys
import json
import copy
import socket

from loguru import logger

from PyQt5.QtCore import (
    QTimer,
    QObject,
    QProcess,
    pyqtSignal
)

from System.Interface import Windows

if sys.platform == "win32":
    ADB_PATH = "System/ADB/adb.exe"

elif sys.platform == "darwin":
    ADB_PATH = "System/ADB/adb-macos"

else:
    ADB_PATH = "System/ADB/adb-linux"

class GlyphSyncer(QObject):
    error_occurred: pyqtSignal = pyqtSignal(str, str)
    device_changed: pyqtSignal = pyqtSignal(list)

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)
        
        self.initialized:      bool            = True
        self.composition:      any             = None
        self.connected_model:  str | None      = None
        self.client_socket:    socket.socket   = None
        
        self.devices:          list            = []
        self.blocked_devices:  list            = []
        self.processes:        list            = []
        self.last_synced:      dict            = {}

        self.scan_timer:       QTimer          = QTimer(self)
        
        self.scan_timer.setInterval(2000)
        self.scan_timer.timeout.connect(self.scan_devices)

    def set_composition(self, composition: any) -> None:
        self.composition = composition

    def start_scanning_loop(self) -> None:
        if self.scan_timer.isActive():
            return

        logger.info("Starting device scanning...")
        self.scan_timer.start()

    def stop_scanning_loop(self) -> None:
        if not self.scan_timer.isActive():
            return

        self.scan_timer.stop()

        for process in list(self.processes):
            try:
                process.kill()
            
            except Exception:
                pass
        
        self.processes.clear()
        logger.success("Device scanning loop stopped. Subprocesses terminated.")

    # Process Management

    def run_command_async(
        self,
        arguments:   list[str],
        on_finished: any = None,
        on_error:    any = None
    ) -> QProcess:
        
        if arguments and arguments[0] != ADB_PATH:
            arguments = [ADB_PATH] + arguments

        process = QProcess(self)
        self.processes.append(process)

        def cleanup() -> None:
            if process in self.processes:
                self.processes.remove(process)
            
            process.deleteLater()

        def finished(
            exit_code:   int,
            exit_status: QProcess.ExitStatus
        ) -> None:
            
            stdout = bytes(process.readAllStandardOutput()).decode(errors = "ignore")
            stderr = bytes(process.readAllStandardError()).decode(errors = "ignore")
            
            if exit_code != 0:
                if on_error:
                    on_error(process, exit_code, stderr)
                
                cleanup()
                
                return

            if on_finished:
                on_finished(process, stdout, stderr)
            
            cleanup()

        process.finished.connect(finished)
        process.start(arguments[0], arguments[1:])
        
        return process

    # Device Scanning

    def scan_devices(self) -> None:
        self.run_command_async(
            ["start-server"],
            on_finished = lambda p, o, e:
            
            self.run_command_async(
                ["devices"],
                on_finished = self.on_devices_listed
            )
        )

    def on_devices_listed(
        self,
        process: QProcess,
        output:  str,
        error:   str
    ) -> None:
        
        lines        = output.strip().splitlines()
        new_list     = [line.split()[0] for line in lines[1:] if "device" in line]

        if self.devices == new_list:
            return

        old_devices  = self.devices
        disconnected = list(set(old_devices) - set(new_list))
        connected    = list(set(new_list) - set(old_devices))
        
        self.devices = new_list

        for device in disconnected:
            if device not in self.blocked_devices:
                continue

            self.blocked_devices.remove(device)

        logger.info(f"Found new devices: {connected}")
        self.device_changed.emit(new_list)

        for device in connected:
            if device in self.blocked_devices:
                continue
            
            self.get_model_async(device)

    def get_model_async(self, device_id: str) -> None:
        def handle_model(p, out, err) -> None:
            model = out.strip()
            if not model:
                return
            
            self.init_device(device_id)

        self.run_command_async(
            ["-s", device_id, "shell", "getprop", "ro.product.model"],
            on_finished = handle_model
        )

    # Connection

    def init_device(
        self,
        device_id: str
    ) -> None:
        
        def check_package(p, out, err) -> None:
            is_installed = out.strip().startswith("package:")
            
            if not is_installed:
                if device_id not in self.blocked_devices:
                    self.blocked_devices.append(device_id)
                self.error_occurred.emit("Oops!", "Receiver not found.")
                return

            commands = [
                (["-s", device_id, "forward", "tcp:7777", "tcp:7777"], None),
                (["shell", "settings", "put", "global", "nt_glyph_interface_debug_enable", "1"], None),
                (["-s", device_id, "shell", "am", "force-stop", "com.glyph.receiver"], None),
                (["-s", device_id, "shell", "am", "start-foreground-service", "-n", "com.glyph.receiver/.MainService"], None),
            ]
            
            self.run_sequence(commands, on_done = lambda: self.wait_for_socket(device_id))

        self.run_command_async(
            ["-s", device_id, "shell", "pm", "path", "com.glyph.receiver"],
            on_finished = check_package
        )

    def run_sequence(
        self,
        command_list: list,
        on_done:      any = None
    ) -> None:
        
        if not command_list:
            if on_done:
                on_done()
            return

        arguments, callback = command_list[0]

        def step_finished(p, out, err) -> None:
            if callback:
                callback(p, out, err)
            self.run_sequence(command_list[1:], on_done = on_done)

        self.run_command_async(arguments, on_finished = step_finished, on_error = lambda p, c, e: step_finished(p, "", e))

    def wait_for_socket(
        self,
        device_id: str
    ) -> None:
        
        attempts = {"count": 0}
        limit    = 10

        def try_connect() -> None:
            attempts["count"] += 1
            
            try:
                sock = socket.create_connection(("127.0.0.1", 7777), timeout = 1)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.sendall(json.dumps({"action": "ping"}).encode() + b"\n")
                
                response = sock.recv(1024).decode().strip()
                
                if response == "pong":
                    if self.client_socket:
                        self.client_socket.close()
                    
                    self.client_socket = sock
                    timer.stop()
                    
                    if self.composition:
                        self.full_load(self.composition.all_glyphs())
                    return

            except Exception:
                pass

            if attempts["count"] >= limit:
                timer.stop()

        timer = QTimer(self)
        timer.setInterval(500)
        timer.timeout.connect(try_connect)
        timer.start()

    # Sync Functions

    def has_active_connection(self) -> bool:
        return bool(set(self.devices) - set(self.blocked_devices))

    def attempt_reconnect(self) -> None:
        if not self.has_active_connection():
            return
            
        try:
            sock = socket.create_connection(("127.0.0.1", 7777), timeout = 2)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            if self.client_socket:
                self.client_socket.close()
            
            self.client_socket = sock
        
        except Exception as error:
            if self.has_active_connection():
                Windows.ErrorWindow("Connection Error", str(error)).exec_()

    def send_payload(
        self,
        payload: dict
    ) -> None:
        
        if not self.has_active_connection():
            return

        if not self.client_socket:
            self.attempt_reconnect()

        if not self.client_socket:
            return

        try:
            self.client_socket.sendall(json.dumps(payload).encode() + b"\n")
        
        except Exception as error:
            if self.client_socket:
                self.client_socket.close()
            self.client_socket = None
            
            if self.has_active_connection():
                Windows.ErrorWindow("Socket Error", str(error)).exec_()

    def sync(
        self,
        current: dict
    ) -> None:
        
        if current is None:
            current = {}
            
        current_data = {str(k): v for k, v in current.items()}
        deleted_ids  = list(set(self.last_synced) - set(current_data))

        def is_changed(old, new) -> bool:
            if old is None:
                return True
            
            fields = ("track", "start", "duration", "brightness", "effect", "segments")
            return any(old.get(key) != new.get(key) for key in fields)

        changed_glyphs = {
            glyph_id: glyph
            for glyph_id, glyph in current_data.items()
            if is_changed(self.last_synced.get(glyph_id), glyph)
        }

        if deleted_ids:
            self.send_payload({"action": "delete", "ids": deleted_ids})

        if changed_glyphs:
            enriched = {}
            
            for glyph_id, glyph in changed_glyphs.items():
                copy_data = glyph.copy()
                
                if "effect" in glyph:
                    effects = self.composition.cached_effects.get(int(glyph_id))
                    
                    if effects:
                        copy_data["effect_to_glyphs"] = effects
                
                enriched[glyph_id] = copy_data
            
            self.send_payload({"action": "update", "glyphs": enriched})

        self.last_synced = copy.deepcopy(current_data)

    def full_load(self, glyphs: dict) -> None:
        if glyphs is None:
            glyphs = {}
        
        enriched = []

        for glyph_id, glyph in glyphs.items():
            item = glyph.copy()
            item["id"] = glyph_id
            
            if "effect" in glyph:
                effects = getattr(self.composition, "cached_effects", {}).get(int(glyph_id))
                
                if effects:
                    item["effect_to_glyphs"] = effects
            
            enriched.append(item)

        self.send_payload({"action": "load", "glyphs": enriched})
        self.last_synced = copy.deepcopy({str(k): v for k, v in glyphs.items()})

    # Control Functions

    def play(self, ms: int) -> None:
        self.send_payload({"action": "play", "from_ms": ms})

    def stop(self) -> None:
        self.send_payload({"action": "stop"})
    
    def set_speed(self, speed: float) -> None:
        self.send_payload({"action": "set_speed", "value": speed})

    def exit_app(self) -> None:
        self.send_payload({"action": "stop_app"})
        
        if self.client_socket:
            self.client_socket.close()
            self.client_socket = None
        
        self.stop_scanning_loop()
    
    def cleanup(self) -> None:
        self.set_composition(None)

rt_visualizer = GlyphSyncer()