import time
import json
import socket
import copy

from System import Utils

from PyQt5.QtCore import *
from System.Constants import *

ADB_PATH = "System/ADB/adb"

class DeviceScanner(QObject):
    device_changed = pyqtSignal(list)
    
    def __init__(self, syncer):
        super().__init__()
        self.syncer = syncer
        self._running = True
        self._timer = None

    @pyqtSlot()
    def run(self):
        if not self._running:
            return

        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self.scan)
        self._timer.start()

    @pyqtSlot()
    def scan(self):
        if not self._running:
            if self._timer:
                self._timer.stop()
            return

        old_devices = self.syncer.devices.copy()
        self.syncer.scan_devices()
        if old_devices != self.syncer.devices:
            self.device_changed.emit(self.syncer.devices)

    def stop(self):
        self._running = False

class GlyphSyncer:
    def __init__(self, composition):
        self.last_synced = {}

        self.composition = composition
        self.connected_model = None
        self.devices = []

        self._scanner_thread = None
        self._scanner_worker = None
        
        self.scan_devices()
        
        if self.devices:
            self.client_sock = socket.create_connection(("127.0.0.1", 7777))
            self.client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    
    def start_scanning_loop(self):
        if self._scanner_thread and self._scanner_thread.isRunning():
            return

        self._scanner_thread = QThread()
        self._scanner_worker = DeviceScanner(self)
        
        self._scanner_worker.moveToThread(self._scanner_thread)
        self._scanner_thread.started.connect(self._scanner_worker.run)

        self._scanner_thread.start()

    def stop_scanning_loop(self):
        if self._scanner_thread and self._scanner_thread.isRunning():
            self._scanner_worker.stop()
            self._scanner_thread.quit()
            self._scanner_thread.wait(3000)

    def _init_worker_timer(self):
        self._scanner_timer = QTimer()
        self._scanner_timer.setInterval(3000)
        self._scanner_timer.timeout.connect(self._scanner_worker.scan)
        self._scanner_timer.start()

    def init_device(self, device_id):
        Utils.run([ADB_PATH, "-s", device_id, "forward", "tcp:7777", "tcp:7777"], check=True)
        Utils.run([ADB_PATH, "shell", "settings", "put", "global", "nt_glyph_interface_debug_enable", "1"])
        Utils.run([ADB_PATH, "shell", "am", "force-stop", "com.glyph.receiver"], check = True)
        #Utils.run([ADB_PATH, "shell", "am", "stopservice", "com.glyph.receiver/.MainService"])
        Utils.run([ADB_PATH, "shell", "am", "start-foreground-service", "-n", "com.glyph.receiver/.MainService"], check = True)

        self.connected_model = self.get_model(device_id)

        is_connected = False
        max_retries = 10
        retry_delay = 1

        for _ in range(max_retries):
            try:
                self.client_sock = socket.create_connection(("127.0.0.1", 7777), timeout=1)
                self.client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                self.client_sock.sendall(json.dumps({"action": "ping"}).encode() + b"\n")

                self.client_sock.settimeout(2) 
                response = self.client_sock.recv(1024).decode().strip()

                if response == "pong":
                    is_connected = True
                    break

            except (ConnectionRefusedError, socket.timeout) as e:
                pass

            time.sleep(retry_delay)

        if not is_connected:
            return

        if hasattr(self.composition, "glyphs"):
            self.full_load(self.composition.all_glyphs())
    
    def get_model(self, device_id):
        result = Utils.run(
            [ADB_PATH, "-s", device_id, "shell", "getprop", "ro.product.model"],
            capture_output=True,
            text=True,
            check=True
        )
        
        return ModelCodes.get(result.stdout.strip())
    
    def scan_devices(self):
        Utils.run([ADB_PATH, "start-server"], check=True)

        result = Utils.run([ADB_PATH, "devices"], capture_output=True, text=True, check=True)
        lines = result.stdout.strip().splitlines()
        devices = [line.split()[0] for line in lines[1:] if "device" in line]
        
        if self.devices != devices:
            old_devices = self.devices
            new_devices = devices

            disconnected = list(set(old_devices) - set(new_devices))
            connected = list(set(new_devices) - set(old_devices))
            
            self.devices = devices
            
            for device in connected:
                if self.get_model(device):
                    self.init_device(device)
                    break
    
    def play(self, ms: int):
        self._send_json(
            {
                "action": "play",
                "from_ms": ms
            }
        )
    
    def stop(self):
        self._send_json({"action": "stop"})

    def _send_json(self, payload: dict):
        if not self.devices:
            return
        
        try:
            self.client_sock.sendall(json.dumps(payload).encode() + b"\n")

        except Exception as e:
            self.client_sock = socket.create_connection(("127.0.0.1", 7777))
            self.client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def sync(self, current: dict):
        print("- - - - - SYNC - - - - -")
        current = {str(k): v for k, v in current.items()}
        deleted = set(self.last_synced) - set(current)
        
        def glyph_changed(g1, g2):
            if g1 is None:
                return True
            
            return any(g1.get(k) != g2.get(k) for k in ("track", "start", "duration", "brightness", "effect", "segments"))

        changed = {
            gid: glyph
            for gid, glyph in current.items()
            if glyph_changed(self.last_synced.get(gid), glyph)
        }

        if deleted:
            self._send_json({"action": "delete", "ids": list(deleted)})
        
        if changed:
            enriched = {}
            for gid, glyph in changed.items():
                glyph_copy = glyph.copy()
                if "effect" in glyph:
                    effect_to_glyphs = self.composition.cached_effects.get(gid)
                    
                    if effect_to_glyphs is not None:
                        glyph_copy["effect_to_glyphs"] = effect_to_glyphs
                
                enriched[gid] = glyph_copy

            self._send_json({"action": "update", "glyphs": enriched})
        
        self.last_synced = {k: copy.deepcopy(v) for k, v in current.items()}

    def full_load(self, glyphs: dict):
        enriched = {}
        for gid, glyph in glyphs.items():
            glyph_copy = glyph.copy()
            
            if "effect" in glyph:
                effect_to_glyphs = self.composition.cached_effects.get(gid)
                
                if effect_to_glyphs is not None:
                    glyph_copy["effect_to_glyphs"] = effect_to_glyphs
            
            enriched[gid] = glyph_copy
        
        payload = {
            "action": "load",
            "glyphs": [
                dict(g, id=k) for k, g in enriched.items()
            ]
        }
        self._send_json(payload)
        self.last_synced = copy.deepcopy(dict(glyphs))
    
    def exit_app(self):
        self._send_json(
            {
                "action": "stop_app"
            }
        )