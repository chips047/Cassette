import sys
import json
import socket
import copy
import weakref

from PyQt5.QtCore import *

from System import UI
from System.Constants import *

if sys.platform == "win32":
    ADB_PATH = "System/ADB/adb.exe"

elif sys.platform == "darwin":
    ADB_PATH = "System/ADB/adb-macos"

else:
    ADB_PATH = "System/ADB/adb-linux"

class GlyphSyncer(QObject):
	error_occurred = pyqtSignal(str, str)
	device_changed = pyqtSignal(list)

	def __init__(self, composition, parent=None):
		super().__init__(parent)
		self.composition = composition
		self.connected_model = None
		self.devices = []
		self.blocked_devices = []
		self.last_synced = {}
		self._scan_timer = QTimer(self)
		self._scan_timer.setInterval(2000)
		self._scan_timer.timeout.connect(self.scan_devices)

		self._processes = []

		self.client_sock = None

		self_weak = weakref.ref(self)
		self._self_weak = self_weak

	def start_scanning_loop(self):
		if not self._scan_timer.isActive():
			print("Scanning started")
			self._scan_timer.start()

	def stop_scanning_loop(self):
		if self._scan_timer.isActive():
			self._scan_timer.stop()

		for p in list(self._processes):
			try:
				p.kill()
			
			except Exception:
				pass
		
		self._processes.clear()

	def _run_cmd_async(self, args, on_finished=None, on_error=None):
		if args and args[0] != ADB_PATH:
			args = [ADB_PATH] + args

		proc = QProcess(self)
		self._processes.append(proc)

		def _cleanup():
			try:
				self._processes.remove(proc)
			
			except ValueError:
				pass
			
			proc.deleteLater()

		def _finished(slot_exitCode, slot_exitStatus):
			stdout = bytes(proc.readAllStandardOutput()).decode(errors="ignore")
			stderr = bytes(proc.readAllStandardError()).decode(errors="ignore")
			
			if slot_exitCode == 0:
				if on_finished:
					try:
						on_finished(proc, stdout, stderr)
					
					except Exception as e:
						print("Callback error:", e)
			
			else:
				if on_error:
					try:
						on_error(proc, slot_exitCode, stderr)
					
					except Exception as e:
						print("Error callback exception:", e)
			
			_cleanup()

		proc.finished.connect(_finished)
		proc.start(args[0], args[1:])
		return proc

	def scan_devices(self):
		if getattr(self, "devices", None) is None:
			return

		def _on_start_server_finished(proc, out, err):
			self._run_cmd_async(["devices"], on_finished=_on_devices)

		def _on_devices(proc, out, err):
			lines = out.strip().splitlines()
			devices = [line.split()[0] for line in lines[1:] if "device" in line]

			if self.devices != devices:
				old_devices = self.devices
				new_devices = devices
				disconnected = list(set(old_devices) - set(new_devices))
				connected = list(set(new_devices) - set(old_devices))
				self.devices = new_devices

				for device in disconnected:
					if device in self.blocked_devices:
						try:
							self.blocked_devices.remove(device)
						
						except ValueError:
							pass

				print(f"New devices: {new_devices}")
				self.device_changed.emit(new_devices)

				for device in connected:
					if device in self.blocked_devices:
						if device in self.devices:
							try:
								self.devices.remove(device)
							
							except ValueError:
								pass
						
						continue

					self._get_model_async(device, callback=lambda model, dev=device: self._on_model_for_new_device(dev, model))

		self._run_cmd_async(["start-server"], on_finished=_on_start_server_finished, on_error=lambda p, code, e: print("adb start-server failed:", e))

	def _get_model_async(self, device_id, callback):
		def _on_finished(proc, out, err):
			model = out.strip()
			try:
				code = ModelCodes.get(model)
			
			except Exception:
				code = None
			
			callback(code)

		self._run_cmd_async(["-s", device_id, "shell", "getprop", "ro.product.model"], on_finished=_on_finished, on_error=lambda p, c, e: callback(None))

	def _on_model_for_new_device(self, device_id, model):
		if not model:
			return
		
		self.init_device(device_id)

	def init_device(self, device_id):
		def _check_package_finished(proc, out, err):
			ok = out.strip().startswith("package:")
			
			if not ok:
				if device_id not in self.blocked_devices:
					self.blocked_devices.append(device_id)
				
				self.error_occurred.emit("Oops!", "We could not find an installed Cassette Receiver on your smartphone. Install it from System/ADB folder.")
				return

			cmds = [
				(["-s", device_id, "forward", "tcp:7777", "tcp:7777"], None),
				(["shell", "settings", "put", "global", "nt_glyph_interface_debug_enable", "1"], None),
				(["-s", device_id, "shell", "am", "force-stop", "com.glyph.receiver"], None),
				(["-s", device_id, "shell", "am", "start-foreground-service", "-n", "com.glyph.receiver/.MainService"], None),
			]
			self._run_sequence(cmds, on_done=lambda: self._wait_for_socket_and_load(device_id))

		self._run_cmd_async(["-s", device_id, "shell", "pm", "path", "com.glyph.receiver"], on_finished=_check_package_finished, on_error=lambda p, c, e: _check_package_finished(p, "", e))

	def _run_sequence(self, cmd_list, on_done=None):
		if not cmd_list:
			if on_done:
				on_done()
			
			return

		args, specific_cb = cmd_list[0]

		def _this_finished(proc, out, err):
			if specific_cb:
				try:
					specific_cb(proc, out, err)
				
				except Exception as e:
					print("specific_cb failed:", e)
			
			self._run_sequence(cmd_list[1:], on_done=on_done)

		self._run_cmd_async(args, on_finished=_this_finished, on_error=lambda p, code, err: _this_finished(p, "", err))

	def _wait_for_socket_and_load(self, device_id):
		max_retries = 10
		retry_delay = 0.5

		attempts = {"n": 0}

		def _try_connect():
			if getattr(self, "_scan_timer", None) is None:
				return

			attempts["n"] += 1
			
			try:
				sock = socket.create_connection(("127.0.0.1", 7777), timeout=1)
				sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
				sock.sendall(json.dumps({"action": "ping"}).encode() + b"\n")
				sock.settimeout(2)
				resp = sock.recv(1024).decode().strip()
				
				if resp == "pong":
					try:
						if self.client_sock:
							try:
								self.client_sock.close()
							
							except Exception:
								pass
						
						self.client_sock = sock
					
					except Exception:
						try:
							sock.close()
						
						except Exception:
							pass
					
					t.stop()
					
					if hasattr(self.composition, "glyphs"):
						self.full_load(self.composition.all_glyphs())
					
					return
			
			except (ConnectionRefusedError, socket.timeout, OSError):
				pass

			if attempts["n"] >= max_retries:
				t.stop()
				return

		t = QTimer(self)
		t.setInterval(int(retry_delay * 1000))
		t.timeout.connect(_try_connect)
		t.start()

	def _has_unblocked_devices(self) -> bool:
		return bool(set(self.devices) - set(self.blocked_devices))

	def attempt_connect(self):
		if not self._has_unblocked_devices():
			return
		try:
			sock = socket.create_connection(("127.0.0.1", 7777), timeout=2)
			sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
			if self.client_sock:
				try:
					self.client_sock.close()
				
				except Exception:
					pass
			
			self.client_sock = sock
		
		except Exception as e:
			if self._has_unblocked_devices():
				error = UI.ErrorWindow("Failed to communicate with Phone", str(e))
				error.exec_()

	def _send_json(self, payload: dict):
		if not self._has_unblocked_devices():
			return

		if not self.client_sock:
			try:
				self.attempt_connect()
			
			except Exception:
				pass

		if not self.client_sock:
			if self._has_unblocked_devices():
				error = UI.ErrorWindow("Failed to communicate with Phone", "No socket available")
				error.exec_()
			
			return

		try:
			self.client_sock.sendall(json.dumps(payload).encode() + b"\n")
		
		except Exception as e:
			try:
				self.client_sock.close()
			
			except Exception:
				pass

			self.client_sock = None
			if self._has_unblocked_devices():
				error = UI.ErrorWindow("Failed to communicate with Phone", str(e))
				error.exec_()

	def sync(self, current: dict):
		if current is None:
			current = {}
		
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
					effect_to_glyphs = getattr(self.composition, "cached_effects", {}).get(gid)
					
					if effect_to_glyphs is not None:
						glyph_copy["effect_to_glyphs"] = effect_to_glyphs
				
				enriched[gid] = glyph_copy
			
			self._send_json({"action": "update", "glyphs": enriched})

		self.last_synced = {k: copy.deepcopy(v) for k, v in current.items()}

	def full_load(self, glyphs: dict):
		if glyphs is None:
			glyphs = {}
		
		enriched = {}

		for gid, glyph in glyphs.items():
			glyph_copy = glyph.copy()
			
			if "effect" in glyph:
				effect_to_glyphs = getattr(self.composition, "cached_effects", {}).get(gid)
				if effect_to_glyphs is not None:
					glyph_copy["effect_to_glyphs"] = effect_to_glyphs
			
			enriched[gid] = glyph_copy

		payload = {
			"action": "load",
			"glyphs": [dict(g, id=k) for k, g in enriched.items()]
		}

		self._send_json(payload)
		self.last_synced = copy.deepcopy(dict(glyphs))

	def play(self, ms: int):
		self._send_json({"action": "play", "from_ms": ms})

	def stop(self):
		self._send_json({"action": "stop"})

	def exit_app(self):
		self._send_json({"action": "stop_app"})
		if self.client_sock:
			self.client_sock.close()
			self.client_sock = None
		
		self.stop_scanning_loop()