"""SiL-Einrichten: ported from D:/003_MeineRepos/silInstaller/silAssistent.py.
InfoSim IT-Shop and Silver wizard workflow; unified siLAssistent dialog style.

Abhängigkeiten: python -m pip install PySide6 selenium pywinauto psutil pywin32
"""

import argparse
# This module is also executed directly by the elevated installer bootstrap.
if __package__ in (None, ""):
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from source.core.config import Config
from source.core.runtime import Runtime
from source.ui.dialogs import Dialogs
from source.silver.updates import SilverUpdates
from source.silver.silent import SilverSilent
import sys
import queue
import threading
import json
import os
import time
import ctypes
import tempfile
import subprocess
from ctypes import wintypes
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import (
    QTimer, QRect, QPropertyAnimation, QSequentialAnimationGroup, QEasingCurve, QEventLoop,
    Qt,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QWidget, QFileDialog, QScrollArea, QSizePolicy,
)

from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException, WebDriverException, StaleElementReferenceException,
    ElementClickInterceptedException, ElementNotInteractableException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support.ui import WebDriverWait


class SilverInstallation:
    """Silver-Abfrage, Installer-Pfad und Start der Installation."""

    INSTALLER_PATH = Config.STATE_DEFAULTS["silverInstallerPath"]
    UPDATE_REQUESTED = False
    PREVIOUS_VERSION = None
    TARGET_VERSION = None
    UNINSTALL_TARGET = None

    @classmethod
    def configure_update(cls, requested=False, previous_version=None, target_version=None, uninstall_target=None):
        cls.UPDATE_REQUESTED = requested
        cls.PREVIOUS_VERSION = previous_version
        cls.TARGET_VERSION = target_version
        cls.UNINSTALL_TARGET = uninstall_target

    @classmethod
    def worker_options(cls):
        args = []
        if cls.TARGET_VERSION:
            args.extend(["--silver-target-version", cls.TARGET_VERSION])
        if cls.UPDATE_REQUESTED:
            args.append("--silver-update")
            if cls.PREVIOUS_VERSION:
                args.extend(["--silver-previous-version", cls.PREVIOUS_VERSION])
            if cls.UNINSTALL_TARGET:
                args.extend(["--silver-uninstall-target", cls.UNINSTALL_TARGET])
        return args

    @classmethod
    def run(cls, ui, installer=None, description="Silver kann jetzt installiert werden."):
        try:
            release = SilverUpdates.release()
        except Exception as error:
            ui.show_message("Silver-Setup nicht verfügbar", str(error))
            return 1
        installer = release["installer_path"]
        setup_name = str(installer).replace("\\", "/").rsplit("/", 1)[-1]
        if ui.ask_question("Wollen Sie Silver installieren?", setup_name):
            return cls.install(ui, installer)
        return 0

    WIZARD_TIMEOUT = 600
    @classmethod
    def license_servers(cls):
        from source.silver.licences import SilverLicences
        return SilverLicences.wizard_value()

    TASK_OPTIONS = (
        ("For the current user only", True),
        ("For the entire system", False),
        ("Set the SILVER_HOME environment variable", True),
        (r"Add SILVER_HOME\bin to the path", True),
        (r"Add SILVER_HOME\common\ext-tools\mingw\bin to the path", True),
        ("Add the Silver Simulink library to the MATLAB path", True),
        ("Install XIL", False),
    )

    @classmethod
    def install(cls, ui, installer=None):
        installer = installer or cls.INSTALLER_PATH
        if not installer:
            installer, _ = QFileDialog.getOpenFileName(
                None, "Silver-Installer auswählen", "", "Windows-Installer (*.exe *.msi)"
            ) 
            if not installer:
                return 0
        messages = queue.Queue()
        cancelled = threading.Event()
        state = {"exit_code": 1, "error": None, "finished": False,
                 "wizard_visible": False, "wait_loop": QEventLoop()}
        progress, body, animation = ui.create_progress_card(
            "Silver installieren", "Netzwerk-Installer wird vorbereitet ...", "Abbrechen"
        )
        request_cancel = lambda: cls.request_cancel(cancelled, body, progress)
        for button in progress.findChildren(QPushButton):
            button.clicked.disconnect()
            button.clicked.connect(request_cancel)
        progress.reject = request_cancel
        progress.closeEvent = lambda event: (event.ignore(), request_cancel())
        progress.keyPressEvent = lambda event: request_cancel() if event.key() == Qt.Key.Key_Escape else event.ignore()
        timer = QTimer(progress)
        timer.setInterval(100)
        timer.timeout.connect(lambda: cls.poll_launch(
            progress, body, animation, timer, messages, state
        ))
        worker = threading.Thread(
            target=cls.launch_worker, args=(installer, messages, cancelled), daemon=True
        )
        worker.start()
        timer.start()
        animation.start()
        try:
            progress.exec()
            if state["wizard_visible"] and not state["finished"] and not cancelled.is_set():
                state["wait_loop"].exec()
        finally:
            timer.stop()
            animation.stop()
            cancelled.set()
            worker.join(timeout=0.2)
        if state["error"]:
            ui.show_message("Silver-Installation nicht gestartet", state["error"])
        return state["exit_code"]

    @classmethod
    def request_cancel(cls, cancelled, body, progress):
        cancelled.set()
        body.setText("Installation wird abgebrochen. Lokale Installer-Kopie wird entfernt ...")
        for button in progress.findChildren(QPushButton):
            button.setEnabled(False)

    @classmethod
    def poll_launch(cls, progress, body, animation, timer, messages, state):
        try:
            while True:
                kind, message = messages.get_nowait()
                body.setText(message)
                print(message, flush=True)
                if kind == "wizard_ready":
                    state["wizard_visible"] = True
                    body.setText("Silver-Wizard geöffnet. Die Installation wird automatisch vorbereitet ...")
                if kind in ("installation_started", "installation_complete", "cancelled", "error"):
                    state["finished"] = True
                    state["exit_code"] = 0 if kind in ("installation_started", "installation_complete", "cancelled") else 1
                    state["error"] = message if kind == "error" else None
                    timer.stop()
                    animation.stop()
                    progress.accept()
                    if state.get("wait_loop"):
                        state["wait_loop"].quit()
                    return
        except queue.Empty:
            pass

    @classmethod
    def launch_worker(cls, installer, messages, cancelled):
        events = []
        known_pids = set()
        local_copy = None
        try:
            messages.put(("status", "Assistent-Worker ist aktiv."))
            if not getattr(cls, "IS_WORKER", False):
                messages.put(("status", "Aktueller Silver-Installerpfad wird aus der Laufwerk-INI gelesen ..."))
                release = SilverUpdates.release()
                if cls.UPDATE_REQUESTED and cls.TARGET_VERSION and release["version"] != cls.TARGET_VERSION:
                    raise RuntimeError("Die Silver-Zielversion auf dem Laufwerk hat sich geändert. Bitte das Update erneut prüfen und bestätigen.")
                SilverUpdates.sync_path(release)
                cls.TARGET_VERSION = release["version"]
                installer = release["installer_path"]
            installer = cls.prepare_local_installer(installer, messages, cancelled)
            local_copy = cls.cached_installer(installer)
            if not getattr(cls, "IS_WORKER", False):
                cls.relay_elevated_worker(installer, messages, cancelled)
                return
            path = Path(installer).expanduser().resolve()
            if not path.is_file() or path.suffix.lower() not in (".exe", ".msi"):
                raise RuntimeError(f"Der Netzwerk-Installer ist nicht erreichbar. Bitte Verbindung und Berechtigungen prüfen.\n{path}")
            request = getattr(cls, "SILENT_REQUEST", None) or SilverSilent.request()
            SilverSilent.validate_request(request)
            SilverSilent.environment()
            SilverSilent.command(path, cls.TARGET_VERSION, request, Path(request["local_app_data"]) / "siLAssistent" / "preflight.log")
            if cls.UPDATE_REQUESTED:
                SilverUpdates.validate_installer(path)
                SilverUpdates.uninstall(cls.UNINSTALL_TARGET, cls.PREVIOUS_VERSION, messages,
                                        cancelled, stop_process=cls.stop_installation)
                cls.record_step(events, "previous_version_uninstalled", version=cls.PREVIOUS_VERSION)
            if cancelled.is_set():
                raise RuntimeError("Silver-Installation abgebrochen.")
            request = getattr(cls, "SILENT_REQUEST", None) or SilverSilent.request()
            ini_path = SilverSilent.run(path, cls.TARGET_VERSION, request, messages, cancelled,
                                       known_pids, lambda stage, **details: cls.record_step(events, stage, **details))
            SilverUpdates.record_success(cls.TARGET_VERSION, ini_path=ini_path)
            cls.record_step(events, "installation_complete", ini_path=str(ini_path))
            cls.remove_local_installer(local_copy)
            messages.put(("installation_complete", "Silver wurde erfolgreich installiert. Lokale Installer-Kopie gelöscht."))
        except Exception as error:
            if known_pids:
                try:
                    cls.stop_installation(known_pids)
                except Exception as stop_error:
                    messages.put(("error", f"{error}\nAbbruch nicht bestätigt: {stop_error}. Installer-Kopie bleibt erhalten."))
                    return
            try:
                cls.remove_local_installer(local_copy)
            except Exception as cleanup_error:
                error = RuntimeError(f"{error}\nInstaller-Kopie konnte nicht gelöscht werden: {cleanup_error}")
                cancelled.clear()
            if cancelled.is_set():
                messages.put(("cancelled", "Installation abgebrochen. Lokale Installer-Kopie gelöscht."))
                return
            message = f"{type(error).__name__}: {error}"
            events.append({"stage": "error", "message": message})
            diagnostic = cls.save_launch_diagnostic(events)
            messages.put(("error", message + f"\nDiagnose: {diagnostic}"))

    @classmethod
    def cached_installer(cls, installer):
        path = Path(installer).resolve()
        cache = getattr(cls, "CACHE_ROOT", (Path(tempfile.gettempdir()) / "silassistent_installers").resolve())
        # Only our private cached executable, never the network source or custom input.
        return path if path.parent == cache else None

    @classmethod
    def remove_local_installer(cls, path):
        if path is None:
            return
        path = Path(path)
        if not path.exists():
            return
        deadline = time.monotonic() + 30
        while True:
            try:
                path.unlink()  # Endgültig löschen, nicht in den Papierkorb verschieben.
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.3)

    @classmethod
    def stop_installation(cls, known_pids):
        import psutil
        processes = []
        for pid in cls.related_process_ids(known_pids):
            try:
                process = psutil.Process(pid)
                if pid != os.getpid():
                    processes.append(process)
            except psutil.NoSuchProcess:
                pass
        # Prefer the installer's own cancellation and rollback before termination.
        from pywinauto import Desktop
        for process in processes:
            for window in Desktop(backend="uia").windows(process=process.pid):
                for button in window.descendants(control_type="Button"):
                    if cls.normalized_label(button.window_text()) in ("cancel", "abbrechen") and button.is_enabled():
                        button.click()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            alive = [p for p in processes if p.is_running()]
            if not alive:
                return
            for process in alive:
                for window in Desktop(backend="uia").windows(process=process.pid):
                    for button in window.descendants(control_type="Button"):
                        if cls.normalized_label(button.window_text()) in ("yes", "ja") and button.is_enabled():
                            button.click()
            time.sleep(0.3)
        for process in processes:
            try:
                process.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(processes, timeout=10)
        if alive:
            raise RuntimeError("Silver-Prozess konnte nicht beendet werden; Installer-Kopie bleibt bis zum Prozessende erhalten.")

    @classmethod
    def wait_installation(cls, handle, known_pids, messages, cancelled):
        import psutil
        from pywinauto import Desktop
        window = Desktop(backend="uia").window(handle=handle)
        completed = False
        while True:
            if cancelled.is_set():
                raise RuntimeError("Silver-Installation abgebrochen.")
            known_pids.update(cls.related_process_ids(known_pids))
            if window.exists():
                text = cls.page_text(window).casefold()
                if "completing the silver setup wizard" in text or "has finished installing silver" in text:
                    if not completed:
                        messages.put(("status", "Silver ist installiert. Bitte den Wizard mit Finish schließen."))
                    completed = True
            alive = any(psutil.pid_exists(pid) for pid in known_pids)
            if not alive:
                if not completed:
                    raise RuntimeError("Silver wurde beendet, ohne einen erfolgreichen Abschluss zu bestätigen.")
                return
            cancelled.wait(0.3)

    @classmethod
    def prepare_local_installer(cls, installer, messages, cancelled):
        source = Path(installer).expanduser()
        if not str(source).startswith("\\\\"):
            return str(source)
        info = source.stat()
        cache = Path(tempfile.gettempdir()) / "silassistent_installers"
        cache.mkdir(parents=True, exist_ok=True)
        target = cache / source.name
        if target.exists() and target.stat().st_size == info.st_size and abs(target.stat().st_mtime - info.st_mtime) < 1:
            messages.put(("status", "Lokaler Silver-Installer ist bereit."))
            return str(target)
        partial = cache / (source.name + f".{os.getpid()}.partial")
        copied = 0
        last_status = 0.0
        messages.put(("status", "Silver-Installer wird vom Netzwerk lokal vorbereitet ..."))
        try:
            with source.open("rb") as incoming, partial.open("wb") as outgoing:
                while True:
                    if cancelled.is_set():
                        raise RuntimeError("Vorbereitung des Silver-Installers abgebrochen.")
                    block = incoming.read(4 * 1024 * 1024)
                    if not block:
                        break
                    outgoing.write(block)
                    copied += len(block)
                    if time.monotonic() - last_status >= 1:
                        messages.put(("status", f"Silver-Installer lokal vorbereiten: {copied * 100 // max(info.st_size, 1)} %"))
                        last_status = time.monotonic()
            if copied != info.st_size:
                raise RuntimeError("Die lokale Installer-Kopie ist unvollständig.")
            os.utime(partial, (info.st_atime, info.st_mtime))
            os.replace(partial, target)
        finally:
            if partial.exists():
                partial.unlink()
        return str(target)

    @classmethod
    def show_wizard(cls, handle):
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user.ShowWindow.restype = wintypes.BOOL
        user.SetForegroundWindow.argtypes = [wintypes.HWND]
        user.SetForegroundWindow.restype = wintypes.BOOL
        user.ShowWindow(handle, 9)  # SW_RESTORE: sichtbar und nicht minimiert.
        user.SetForegroundWindow(handle)

    @classmethod
    def is_administrator(cls):
        return os.name == "nt" and bool(ctypes.windll.shell32.IsUserAnAdmin())

    @classmethod
    def worker_launch_command(cls, bootstrap, result_path, installer):
        interpreter=Path(sys.executable)
        if getattr(sys,"frozen",False) or "__compiled__" in globals():
            if interpreter.name.casefold() in ("python.exe","pythonw.exe","py.exe"):
                raise RuntimeError("Das Anwendungspaket ist unvollständig: Der Installations-Worker muss über siLAssistent.exe gestartet werden.")
            arguments=["--Assistent-Worker-result",str(result_path),"--silver-installer",str(installer)]+cls.worker_options()
        else:
            pythonw=interpreter.with_name("pythonw.exe")
            if pythonw.exists():
                interpreter=pythonw
            arguments=[str(bootstrap),str(Path(__file__).resolve()),str(result_path),str(installer)]+cls.worker_options()
        return interpreter,subprocess.list2cmdline(arguments)

    @classmethod
    def relay_elevated_worker(cls, installer, messages, cancelled):
        # Nur der Assistent-Worker wird erhöht, nicht der IT-Shop-Browser.
        directory = Path(tempfile.mkdtemp(prefix="silassistent_silver_"))
        # Explizite Rechte für die normale GUI, auch wenn der erhöhte Worker
        # Dateien durch atomaren Austausch mit einem anderen Eigentümer erstellt.
        # Windows liefert die SID ohne zusätzliche Python-Pakete.
        identity = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"], check=True,
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
        ).stdout.decode("utf-8", errors="replace")
        import re
        match = re.search(r"S-1-[0-9-]+", identity)
        if not match:
            raise RuntimeError("Windows-Benutzer-SID konnte nicht ermittelt werden.")
        sid = match.group(0)
        subprocess.run(["icacls", str(directory), "/grant", f"*{sid}:(OI)(CI)F"],
                       check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        result_path = directory / "worker.json"
        (directory / "request.json").write_text(json.dumps(SilverSilent.request(sid)), encoding="utf-8")
        bootstrap = directory / "start_worker.py"
        bootstrap.write_text(
            "import sys, pathlib, runpy, json, traceback\n"
            "source, result, installer = sys.argv[1:4]\n"
            "log = open(str(pathlib.Path(result).with_suffix('.log')), 'a', encoding='utf-8', buffering=1)\n"
            "sys.stdout = sys.stderr = log\n"
            "sys.argv = [source, '--Assistent-Worker-result', result, '--silver-installer', installer] + sys.argv[4:]\n"
            "try:\n"
            "    runpy.run_path(source, run_name='__main__')\n"
            "except SystemExit as error:\n"
            "    if error.code not in (None, 0) and not pathlib.Path(result).exists():\n"
            "        pathlib.Path(result).write_text(json.dumps([['error', 'Worker beendet: ' + str(error.code)]]), encoding='utf-8')\n"
            "except BaseException:\n"
            "    message = traceback.format_exc()\n"
            "    print(message)\n"
            "    pathlib.Path(result).write_text(json.dumps([['error', message]]), encoding='utf-8')\n",
            encoding="utf-8"
        )
        interpreter,arguments=cls.worker_launch_command(bootstrap,result_path,installer)
        messages.put(("status", "Windows-Freigabe für die automatische Silver-Installation erforderlich ..."))
        if not (getattr(sys,"frozen",False) or "__compiled__" in globals()):
            messages.put(("status","Die Admin-Abfrage betrifft den bereits installierten Python-Interpreter für den Silver-Worker. Es wird kein Python installiert."))
        else:
            messages.put(("status","Die Admin-Abfrage betrifft den siLAssistent-Worker für die Silver-Installation."))
        cls.shell_launch(interpreter, parameters=arguments, verb="open" if cls.is_administrator() else "runas", show=1)
        messages.put(("status", "Admin-Freigabe erteilt. Assistent-Worker wird gestartet ..."))
        delivered = 0
        startup_deadline = time.monotonic() + 90
        deadline = time.monotonic() + cls.WIZARD_TIMEOUT + 600
        cancel_requested = False
        while True:
            if cancelled.is_set() and not cancel_requested:
                result_path.with_suffix(".cancel").touch()
                cancel_requested = True
                messages.put(("status", "Abbruch an den erhöhten Installer übermittelt ..."))
            if result_path.exists():
                try:
                    events = json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    events = []
                for kind, message in events[delivered:]:
                    messages.put((kind, message))
                    delivered += 1
                    if kind in ("installation_started", "installation_complete", "cancelled", "error"):
                        return
            if delivered == 0 and time.monotonic() >= startup_deadline:
                raise RuntimeError(f"Der Assistent-Worker hat keine Startrückmeldung geliefert. Startprotokoll: {result_path.with_suffix('.log')}")
            if time.monotonic() >= deadline:
                raise RuntimeError("Der erhöhte Assistent-Worker antwortet nicht. Bitte Windows-Freigabe prüfen.")
            time.sleep(0.2)

    @classmethod
    def helper_main(cls, result_file, installer):
        cls.IS_WORKER = True
        if Path(installer).parent.name == "silassistent_installers":
            cls.CACHE_ROOT = Path(installer).parent.resolve()
        result_path = Path(result_file)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        request_file = result_path.with_name("request.json")
        try:
            cls.SILENT_REQUEST = json.loads(request_file.read_text(encoding="utf-8"))
            SilverSilent.validate_request(cls.SILENT_REQUEST)
        except Exception as error:
            result_path.write_text(json.dumps([["error", f"Silver-Installationsauftrag ungültig: {error}"]]), encoding="utf-8")
            return 1
        cancelled = threading.Event()
        messages = queue.Queue()
        events = []
        if not cls.is_administrator():
            result_path.write_text(json.dumps([["error", "Windows hat dem Assistent-Worker keine erhöhten Rechte erteilt."]]), encoding="utf-8")
            return 1
        worker = threading.Thread(target=cls.launch_worker,
                                  args=(installer, messages, cancelled), daemon=True)
        worker.start()
        while True:
            if result_path.with_suffix(".cancel").exists():
                cancelled.set()
            try:
                kind, message = messages.get(timeout=0.2)
            except queue.Empty:
                if not worker.is_alive():
                    kind, message = "error", "Assistent-Worker wurde ohne Ergebnis beendet."
                else:
                    continue
            events.append([kind, message])
            temporary = result_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, result_path)
            if kind in ("installation_complete", "cancelled", "error"):
                return 0 if kind in ("installation_complete", "cancelled") else 1

    @classmethod
    def normalized_label(cls, text):
        return " ".join(text.replace("&", "").strip(" <>\t\r\n").casefold().split())

    @classmethod
    def page_text(cls, window):
        return "\n".join(control.window_text()[:600] for control in
                         window.descendants(control_type="Text") if control.is_visible())

    @classmethod
    def wait_page(cls, window, heading, cancelled, timeout=40):
        deadline = time.monotonic() + timeout
        while not cancelled.is_set():
            if not window.exists():
                raise RuntimeError("Der Silver-Assistent wurde geschlossen.")
            text = cls.page_text(window)
            if heading.casefold() in text.casefold():
                return text
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Erwartete Silver-Seite nicht gefunden: {heading}. Aktuelle Seite: {text[:500]}")
            cancelled.wait(0.2)
        raise RuntimeError("Silver-Automation abgebrochen.")

    @classmethod
    def find_control(cls, window, names, control_types):
        expected = {cls.normalized_label(name) for name in names}
        found = []
        for control in window.descendants():
            if control.element_info.control_type not in control_types:
                continue
            if not control.is_visible() and not (
                control.element_info.control_type in ("CheckBox", "RadioButton", "ListItem", "TreeItem")
                and control.parent().is_visible()
            ):
                continue
            if cls.normalized_label(control.window_text()) in expected:
                found.append(control)
        if len(found) != 1:
            raise RuntimeError(f"Silver-Bedienelement nicht eindeutig: {names} (gefunden: {len(found)}).")
        return found[0]

    @classmethod
    def checked_state(cls, control):
        try:
            return bool(control.iface_toggle.CurrentToggleState == 1)
        except Exception:
            pass
        try:
            return bool(control.legacy_properties()["State"] & 0x10)
        except Exception:
            pass
        try:
            from pywinauto import uia_defines
            legacy = uia_defines.get_elem_interface(control.element_info.element, "LegacyIAccessible")
            return bool(legacy.CurrentState & 0x10)
        except Exception:
            pass
        # Highlighting a checklist row is not the checkbox's checked state.
        if control.element_info.control_type == "RadioButton":
            try:
                return bool(control.iface_selection_item.CurrentIsSelected)
            except Exception:
                pass
        raise RuntimeError(f"Auswahlstatus kann nicht geprüft werden: {control.window_text()}")

    @classmethod
    def prepare_option(cls, control):
        try:
            control.iface_virtualized_item.Realize()
        except Exception:
            pass
        try:
            control.iface_scroll_item.ScrollIntoView()
        except Exception:
            pass

    @classmethod
    def keyboard_option(cls, control):
        from pywinauto import uia_defines, keyboard
        legacy = uia_defines.get_elem_interface(control.element_info.element, "LegacyIAccessible")
        # MSAA selects/focuses the named child of Inno's custom checklist.
        # No screen coordinates, scaling assumptions or fixed row numbers.
        control.top_level_parent().set_focus()
        legacy.Select(0x1 | 0x2)
        if not legacy.CurrentState & 0x4:  # STATE_SYSTEM_FOCUSED
            raise RuntimeError("Der Optionsfokus konnte nicht bestätigt werden.")
        keyboard.send_keys(" ", pause=0.05)

    @classmethod
    def native_checkbox(cls, control):
        # Inno's owner-drawn TNewCheckListBox may ignore UIA/MSAA actions.
        # Locate its actual native parent and the checkbox's live row bounds.
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT,
                                           ctypes.c_size_t, ctypes.c_ssize_t,
                                           wintypes.UINT, wintypes.UINT,
                                           ctypes.POINTER(ctypes.c_size_t)]
        user.SendMessageTimeoutW.restype = ctypes.c_ssize_t
        ancestor = control
        handle = 0
        classname = ""
        for _ in range(12):
            handle = getattr(ancestor.element_info, "handle", 0) or 0
            if handle:
                buffer = ctypes.create_unicode_buffer(256)
                user.GetClassNameW(handle, buffer, len(buffer))
                classname = buffer.value.casefold()
                if "checklistbox" in classname or classname == "button":
                    break
            ancestor = ancestor.parent()
        else:
            raise RuntimeError("Native Silver-Checkbox konnte nicht zugeordnet werden.")
        output = ctypes.c_size_t()
        send = lambda message, wparam=0, lparam=0: cls.send_native_checkbox(user, handle, output, message, wparam, lparam)
        if classname == "button":
            send(0x00F5)  # BM_CLICK; no mouse, focus or screen coordinates.
            return
        rect = control.rectangle()
        height = rect.bottom - rect.top
        if height <= 0:
            raise RuntimeError("Checkbox-Zeile besitzt keine gültigen Grenzen.")
        # The glyph is at the leading edge of the accessible row. Its centre
        # follows the actual row height, including DPI/font scaling.
        point = wintypes.POINT(rect.left + height // 2, rect.top + height // 2)
        if not user.ScreenToClient(handle, ctypes.byref(point)):
            raise RuntimeError("Checkbox-Koordinaten konnten nicht umgerechnet werden.")
        client = wintypes.RECT()
        user.GetClientRect(handle, ctypes.byref(client))
        if not (client.left <= point.x < client.right and client.top <= point.y < client.bottom):
            raise RuntimeError("Checkbox liegt außerhalb des sichtbaren Listenbereichs.")
        packed = (point.y & 0xffff) << 16 | (point.x & 0xffff)
        send(0x0201, 1, packed)  # WM_LBUTTONDOWN to the identified checklist.
        send(0x0202, 0, packed)  # WM_LBUTTONUP. The checked state is then verified.

    @classmethod
    def send_native_checkbox(cls, user, handle, output, message, wparam=0, lparam=0):
        if not user.SendMessageTimeoutW(handle, message, wparam, lparam, 0x2, 2000, ctypes.byref(output)):
            raise RuntimeError("Native Checkbox antwortet nicht.")

    @classmethod
    def wizard_control_diagnostic(cls, handle):
        from pywinauto import Desktop
        rows = []
        try:
            controls = Desktop(backend="uia").window(handle=handle).descendants()
        except Exception as error:
            return [{"error": str(error)}]
        for control in controls:
            try:
                row = {"text": control.window_text(), "type": control.element_info.control_type,
                       "visible": control.is_visible(), "enabled": control.is_enabled()}
                try:
                    row["legacy"] = control.legacy_properties()
                    row["handle"] = getattr(control.element_info, "handle", 0)
                    row["rectangle"] = str(control.rectangle())
                except Exception:
                    pass
                rows.append(row)
            except Exception as error:
                rows.append({"error": str(error)})
        return rows

    @classmethod
    def set_option(cls, window, names, selected):
        if isinstance(names, str):
            names = (names,)
        control = cls.find_control(window, names, ("CheckBox", "RadioButton", "ListItem", "TreeItem"))
        cls.prepare_option(control)
        if cls.checked_state(control) == selected:
            return
        if not control.is_enabled():
            raise RuntimeError(f"Gesperrte Silver-Option hat falschen Zustand: {names}")
        # Inno Setup exposes some radio/check boxes without UIA Toggle or
        # SelectionItem patterns. Use the actual identified control as fallback.
        from pywinauto import uia_defines
        actions = (
            lambda: control.iface_toggle.Toggle(),
            lambda: uia_defines.get_elem_interface(
                control.element_info.element, "LegacyIAccessible").DoDefaultAction(),
            lambda: cls.keyboard_option(control),
            lambda: cls.native_checkbox(control),
        )
        errors = []
        for action in actions:
            if cls.checked_state(control) == selected:
                return
            try:
                action()
            except Exception as error:
                errors.append(type(error).__name__)
                # An action can change state even if the provider reports an error.
                if cls.checked_state(control) == selected:
                    return
                continue
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                if cls.checked_state(control) == selected:
                    return
                time.sleep(0.1)
        raise RuntimeError(
            f"Silver-Option konnte nicht gesetzt werden: {names}; "
            f"erwartet={selected}, aktuell={cls.checked_state(control)}, "
            f"Steuerelement={control.element_info.control_type}, Versuche={errors}"
        )

    @classmethod
    def click_button(cls, window, name):
        button = cls.find_control(window, (name,), ("Button",))
        if not button.is_enabled():
            raise RuntimeError(f"Silver-Button ist gesperrt: {name}")
        try:
            button.invoke()
        except Exception:
            try:
                from pywinauto import uia_defines
                uia_defines.get_elem_interface(button.element_info.element, "LegacyIAccessible").DoDefaultAction()
            except Exception:
                button.click()

    @classmethod
    def select_components(cls, window):
        combos = [control for control in window.descendants(control_type="ComboBox")
                  if control.is_visible()]
        if len(combos) != 1:
            raise RuntimeError("Installationsart 'Full Installation' nicht eindeutig gefunden.")
        combos[0].select("Full Installation")
        if cls.normalized_label(combos[0].selected_text() or "") != "full installation":
            raise RuntimeError("Full Installation wurde nicht übernommen.")
        for component in ("Silver Utility Modules", "Silver Export Tools", "Examples"):
            cls.set_option(window, component, True)

    @classmethod
    def replace_license_servers(cls, edit, servers):
        # Never append to values retained by a previous Silver installation.
        try:
            edit.set_edit_text("")
        except Exception:
            pass
        if edit.get_value() != "":
            try:
                edit.iface_value.SetValue("")
            except Exception:
                pass
        if edit.get_value() != "":
            try:
                edit.set_focus()
                edit.type_keys("^a{BACKSPACE}")
            except Exception:
                pass
        if edit.get_value() != "":
            raise RuntimeError("Vorhandene Lizenzserver konnten nicht vollständig gelöscht werden. Es wurden keine weiteren Server angehängt.")
        try:
            edit.iface_value.SetValue(servers)
        except Exception:
            edit.set_edit_text(servers)
        if edit.get_value() != servers:
            raise RuntimeError("Die Lizenzserver entsprechen nicht exakt der vorgegebenen Liste. Der automatische Installationsschritt wurde gestoppt.")

    @classmethod
    def configure_license(cls, window):
        edits = [control for control in window.descendants(control_type="Edit")
                 if control.is_visible() and control.is_enabled()]
        if len(edits) != 1:
            raise RuntimeError("FLEXlm-Lizenzserver-Eingabefeld nicht eindeutig gefunden.")
        servers=cls.license_servers()
        cls.replace_license_servers(edits[0],servers)
        cls.set_option(window, ("Enable license queuing", "Enable licence queuing"), True)
        cls.set_option(window, "Suppress license expiration warning dialog", False)

    @classmethod
    def record_step(cls, events, name, **details):
        events.append({"stage": name, **details})
        cls.save_launch_diagnostic(events)

    @classmethod
    def automate_wizard(cls, handle, messages, cancelled, events):
        from pywinauto import Desktop
        window = Desktop(backend="uia").window(handle=handle)
        window.wait("visible enabled", timeout=30)
        cls.show_wizard(handle)
        cls.wait_page(window, "Welcome to the Silver Setup Wizard", cancelled)
        cls.record_step(events, "welcome")
        cls.click_button(window, "Next")
        cls.wait_page(window, "License Agreement", cancelled)
        # Vom Benutzer ausdrücklich angefordert; keine automatische Live-Abnahme im Test.
        cls.set_option(window, "I accept the agreement", True)
        cls.record_step(events, "agreement_selected")
        cls.click_button(window, "Next")
        cls.wait_page(window, "Select Destination Location", cancelled)
        cls.record_step(events, "default_destination_kept")
        cls.click_button(window, "Next")
        cls.wait_page(window, "Select Components", cancelled)
        cls.select_components(window)
        cls.record_step(events, "full_installation_selected")
        cls.click_button(window, "Next")
        cls.wait_page(window, "Select Additional Tasks", cancelled)
        for label, selected in cls.TASK_OPTIONS:
            cls.set_option(window, label, selected)
        # Verify the complete page before moving on, including locked checked items.
        for label, selected in cls.TASK_OPTIONS:
            control = cls.find_control(window, (label,), ("CheckBox", "RadioButton", "ListItem", "TreeItem"))
            if cls.checked_state(control) != selected:
                raise RuntimeError(f"Silver-Zusatzoption wurde nicht übernommen: {label}")
        cls.record_step(events, "additional_tasks_set", options=list(cls.TASK_OPTIONS))
        cls.click_button(window, "Next")
        cls.wait_page(window, "Select a destination for the demos", cancelled)
        cls.record_step(events, "default_demo_destination_kept")
        cls.click_button(window, "Next")
        cls.wait_page(window, "License Configuration", cancelled)
        cls.configure_license(window)
        cls.record_step(events, "license_configured", servers=cls.license_servers(), queuing=True)
        cls.click_button(window, "Next")
        cls.wait_page(window, "Ready to Install", cancelled)
        cls.record_step(events, "ready_to_install")
        if cancelled.is_set():
            raise RuntimeError("Silver-Automation vor Install abgebrochen.")
        cls.click_button(window, "Install")
        cls.wait_page(window, "Installing", cancelled)
        cls.record_step(events, "installation_started")

    @classmethod
    def shell_launch(cls, path, parameters=None, verb="open", show=1):
        if os.name != "nt":
            raise RuntimeError("Der Silver-Installer kann nur unter Windows gestartet werden.")
        class ShellExecuteInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG),
                ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR),
                ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int),
                ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE),
                ("hProcess", wintypes.HANDLE),
            ]
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        ole = ctypes.WinDLL("ole32", use_last_error=True)
        ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        ole.CoInitializeEx.restype = ctypes.c_long
        ole.CoUninitialize.argtypes = []
        ole.CoUninitialize.restype = None
        shell.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
        shell.ShellExecuteExW.restype = wintypes.BOOL
        kernel.GetProcessId.argtypes = [wintypes.HANDLE]
        kernel.GetProcessId.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        initialized = ole.CoInitializeEx(None, 0x2 | 0x4) >= 0
        info = ShellExecuteInfo()
        info.cbSize = ctypes.sizeof(info)
        # Handle erhalten, Shell-Start abwarten, Fehler im eigenen Qt-Fenster anzeigen.
        # Sicherheitsabfragen bleiben aktiv. Kein erhöhtes Recht erzwingen.
        info.fMask = 0x40 | 0x100 | 0x400
        info.lpVerb = verb
        info.lpFile = str(path)
        info.lpParameters = parameters
        info.nShow = show
        try:
            if not shell.ShellExecuteExW(ctypes.byref(info)):
                error_code = ctypes.get_last_error()
                if error_code == 1223:
                    raise RuntimeError("Die Windows-Admin-Abfrage wurde abgebrochen.")
                raise ctypes.WinError(error_code)
            return int(kernel.GetProcessId(info.hProcess)) if info.hProcess else 0
        finally:
            if info.hProcess:
                kernel.CloseHandle(info.hProcess)
            if initialized:
                ole.CoUninitialize()

    @classmethod
    def related_process_ids(cls, known):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        class ProcessEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
            ]
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        kernel.Process32FirstW.restype = wintypes.BOOL
        kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        kernel.Process32NextW.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            return set(known)
        parents = {}
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        try:
            available = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while available:
                parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                available = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)
        related = set(known)
        while True:
            children = {pid for pid, parent in parents.items() if parent in related}
            if children <= related:
                return related
            related.update(children)

    @classmethod
    def visible_windows(cls):
        user = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user.EnumWindows.restype = wintypes.BOOL
        user.EnumChildWindows.argtypes = [wintypes.HWND, callback_type, wintypes.LPARAM]
        user.EnumChildWindows.restype = wintypes.BOOL
        user.IsWindowVisible.argtypes = [wintypes.HWND]
        user.IsWindowVisible.restype = wintypes.BOOL
        user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user.GetWindowTextW.restype = ctypes.c_int
        user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user.GetClassNameW.restype = ctypes.c_int
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user.GetWindowThreadProcessId.restype = wintypes.DWORD
        windows = []
        callback = callback_type(lambda handle, extra: cls.collect_window(user, callback_type, windows, handle, extra))
        user.EnumWindows(callback, 0)
        return windows

    @classmethod
    def collect_window(cls, user, callback_type, windows, handle, extra):
        if not user.IsWindowVisible(handle):
            return True
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if pid.value == os.getpid():
            return True
        title = ctypes.create_unicode_buffer(1024)
        user.GetWindowTextW(handle, title, len(title))
        if not title.value:
            return True
        controls = []
        callback = callback_type(lambda child, value: cls.collect_child(user, controls, child, value))
        user.EnumChildWindows(handle, callback, 0)
        windows.append({"handle": int(handle), "pid": int(pid.value), "title": title.value, "buttons": controls})
        return True

    @classmethod
    def collect_child(cls, user, controls, child, extra):
        if user.IsWindowVisible(child):
            name = ctypes.create_unicode_buffer(128)
            user.GetClassNameW(child, name, len(name))
            if "button" in name.value.lower():
                text = ctypes.create_unicode_buffer(256)
                user.GetWindowTextW(child, text, len(text))
                controls.append(text.value)
        return True

    @classmethod
    def find_wizard(cls, windows, before, related):
        for window in windows:
            if window["handle"] in before:
                continue
            title = window["title"].casefold()
            if window["pid"] not in related and "silver" not in title:
                continue
            if not any(word in title for word in ("silver", "setup", "install", "wizard", "assistent")):
                continue
            buttons = [text.replace("&", "").strip().casefold() for text in window["buttons"]]
            wizard_controls = any(text == "ok" or any(word in text for word in
                                  ("next", "weiter", "install")) for text in buttons)
            wizard_title = any(word in title for word in
                               ("setup wizard", "setup-assistent", "installationsassistent"))
            if wizard_controls or wizard_title:
                return window
        return None

    @classmethod
    def save_launch_diagnostic(cls, events):
        path = Runtime.data_root() / "silver_installation_diagnose.json"
        try:
            path.write_text(json.dumps({"events": events}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            return str(path)
        except OSError as error:
            return f"Diagnose konnte nicht gespeichert werden: {error}"


class SilEinrichten:
    INFOSIM_QUESTION = "Haben Sie InfoSim auf dem Ziel-Rechner installiert?"
    INFOSIM_DESCRIPTION = (
        "Wenn Sie InfoSim zum ersten Mal hören, dann brauchen Sie es definitiv :)\n\n"
        "InfoSim ist ein Rechner-gebundener Dienst!\n\n"
        "Wenn Sie mit SiL auf einem anderen Rechner arbeiten wollen, kann die Installation notwendig sein."
    )
    HOME_URL = "https://itshop.app.corpintra.net/itshop/home/"
    WORKPLACE_URL = "https://itshop.app.corpintra.net/itshop/uss/workplace"
    PRODUCT_URL = (
        "https://itshop.app.corpintra.net/itshop/shop/services/1003099"
        "?filterPattern=Mercedes$0020Benz$0020InfoSim$0020Client$00204.0.0$0020ENU"
    )
    PRODUCT_NAME = "Mercedes Benz InfoSim Client 4.0.0 ENU"
    TIMEOUT = 180
    SHOW_PROGRESS = True
    UI_STYLE = Dialogs.style()
    CART_BUTTON_SELECTOR = 'button.btn-success[data-url*="/AddToCartAction/"]'
    CART_RESPONSE_TIMEOUT = 30

    @classmethod
    def installed_edge_version(cls):
        import winreg, re
        version = None
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for flags in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Edge\BLBeacon", 0,
                                        winreg.KEY_READ | flags) as key:
                        value = winreg.QueryValueEx(key, "version")[0]
                    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", value):
                        version = value
                        break
                except OSError:
                    continue
            if version:
                break
        if not version:
            raise RuntimeError("Installierte Edge-Version konnte nicht ermittelt werden.")
        return version

    @classmethod
    def download_edge_driver(cls):
        import urllib.request, zipfile, io, re
        version = cls.installed_edge_version()
        cache = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "silAssistent" / "drivers"
        cache.mkdir(parents=True, exist_ok=True)
        target = cache / version / "msedgedriver.exe"
        if target.is_file():
            return str(target)
        base = "https://msedgedriver.microsoft.com/"
        versions = [version]
        # Browser patch releases and WebDriver patch releases may differ.
        try:
            with urllib.request.urlopen(base + "LATEST_RELEASE_" + version.split(".")[0] + "_WINDOWS", timeout=15) as response:
                data = response.read()
                latest = data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig").strip()
            if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", latest) and latest.split(".")[:3] == version.split(".")[:3]:
                versions.append(latest)
        except Exception:
            pass
        errors = []
        for matching in dict.fromkeys(versions):
            try:
                with urllib.request.urlopen(base + matching + "/edgedriver_win64.zip", timeout=25) as response:
                    archive = response.read()
                with zipfile.ZipFile(io.BytesIO(archive)) as package:
                    content = package.read("msedgedriver.exe")
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(f".{os.getpid()}.tmp")
                temporary.write_bytes(content)
                os.replace(temporary, target)
                return str(target)
            except Exception as error:
                errors.append(str(error))
        raise RuntimeError(f"Edge {version}: passender Treiber konnte nicht von Microsoft geladen werden: {'; '.join(errors)}")

    @classmethod
    def create_edge_driver(cls, options, driver_path=None):
        if driver_path:
            return webdriver.Edge(service=Service(executable_path=driver_path), options=options)
        directory = Runtime.project_root()
        packaged_root = Path(getattr(sys, "_MEIPASS", directory)) / "drivers"
        prefix = ""
        try:
            prefix = ".".join(cls.installed_edge_version().split(".")[:3]) + "."
            bundled = sorted(path for path in packaged_root.glob("*/msedgedriver.exe")
                             if path.parent.name.startswith(prefix))
        except RuntimeError:
            bundled = []
        candidates = [directory / "msedgedriver.exe", *bundled]
        # Support the previous single-driver layout when running the source.
        if not bundled:
            candidates.append(packaged_root / "msedgedriver.exe")
        failures = []
        from source.core.driver_archive import DriverArchive
        archives=sorted(path for path in packaged_root.glob("*/edgedriver.zip") if prefix and path.parent.name.startswith(prefix))
        for archive in archives:
            try:candidates.append(DriverArchive.unpack(archive))
            except Exception as error:failures.append("Offline-Treiber: "+str(error))
        for path in dict.fromkeys(candidates):
            if not path.is_file():
                continue
            service = Service(executable_path=str(path))
            try:
                return webdriver.Edge(service=service, options=options)
            except WebDriverException as error:
                service.stop()
                failures.append(f"{path.name}: {error}")
        # Edge versions differ between machines; Manager remains the update fallback.
        try:
            return webdriver.Edge(service=Service(), options=options)
        except WebDriverException as error:
            failures.append(f"Selenium Manager: {error}")
            try:
                downloaded = cls.download_edge_driver()
                return webdriver.Edge(service=Service(executable_path=downloaded), options=options)
            except Exception as download_error:
                failures.append(f"Microsoft-Treiberdownload: {download_error}")
            raise RuntimeError(
                "Kein passender Microsoft-Edge-Treiber verfügbar. "
                "Die EXE enthält mehrere Edge-Treiberversionen (148 bis 152). "
                "Die automatische Versionssuche und der Microsoft-Download sind fehlgeschlagen. Bitte einen passenden "
                "msedgedriver.exe neben silAssistent.exe ablegen. "
                "Die ersten drei Versionsnummern müssen zu Edge passen.\n\n"
                + "\n".join(failures)
            ) from error

    @classmethod
    def create_browser(cls, driver_path=None):
        options = webdriver.EdgeOptions()
        options.page_load_strategy = "eager"
        options.add_argument("--start-maximized")
        options.add_experimental_option("detach", True)
        # Kein Benutzername, Passwort oder benutzerspezifischer Profilpfad.
        driver = cls.create_edge_driver(options, driver_path)
        driver.set_page_load_timeout(cls.TIMEOUT)
        return driver

    @classmethod
    def open_page(cls, driver, url):
        print(f"Öffne: {url}")
        driver.get(url)
        # Bei SSO-Weiterleitungen kann sich der Benutzer im Browser anmelden.
        try:
            WebDriverWait(driver, cls.TIMEOUT).until(
                lambda browser: (
                    cls.matches_page(browser.current_url, url)
                    and browser.execute_script("return document.readyState")
                    in ("interactive", "complete")
                )
            )
        except TimeoutException as error:
            actual = urlsplit(driver.current_url)
            raise RuntimeError(
                f"Warten auf die Seite abgebrochen. Aktueller Pfad: {actual.path}; "
                f"erwarteter Pfad: {urlsplit(url).path}"
            ) from error
        print(f"Seite bereit: {urlsplit(driver.current_url).path}")

    @classmethod
    def matches_page(cls, current_url, requested_url):
        current = urlsplit(current_url)
        target = urlsplit(requested_url)
        if current.scheme != target.scheme or current.netloc != target.netloc:
            return False
        current_path = current.path.rstrip("/")
        target_path = target.path.rstrip("/")
        if requested_url == cls.HOME_URL:
            # SSO kann auf /itshop/home/<benutzerbezogene ID> zurückführen.
            return current_path == target_path or current_path.startswith(target_path + "/")
        if requested_url == cls.WORKPLACE_URL:
            # Die Zwischenstation darf innerhalb des IT-Shops weiterleiten.
            # Danach wird die Produktsuche explizit aufgerufen.
            return current_path == "/itshop" or current_path.startswith("/itshop/")
        if requested_url == cls.PRODUCT_URL:
            # Die Shop-Anwendung darf die Route umschreiben. Der tatsächliche
            # Warenkorb-Button wird anschließend separat abgewartet.
            return current_path == "/itshop/shop" or current_path.startswith("/itshop/shop/")
        return current_path == target_path

    @classmethod
    def click_add_to_cart(cls, driver):
        print("Warte auf den vollständig geladenen, aktiven InfoSim-Warenkorb-Button ...", flush=True)
        cls.save_button_diagnostic(driver, "before_wait")
        try:
            element = WebDriverWait(
                driver, cls.TIMEOUT, ignored_exceptions=(StaleElementReferenceException,)
            ).until(cls.find_cart_button)
        except TimeoutException as error:
            diagnostic = cls.save_button_diagnostic(driver, "button_not_ready")
            raise RuntimeError(
                "Der grüne AddToCartAction-Button ist nicht sichtbar oder noch gesperrt "
                "(disabled/CSS disabled). Kein Klick ausgeführt. "
                f"Button-Diagnose: {diagnostic}"
            ) from error
        # Ein bereits geöffneter Hauptservice-Dialog bestätigt die Aktion schon.
        existing = cls.cart_action_response(driver, "")
        if existing:
            return existing
        before_cart = cls.cart_header_text(driver)
        cls.save_button_diagnostic(driver, "ready_before_click")
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element
        )
        try:
            element.click()
        except (ElementClickInterceptedException, ElementNotInteractableException):
            # Native Mausereignisse verwenden; keine deaktivierten Buttons
            # per JavaScript aktivieren und keine Doppelbestellung riskieren.
            ActionChains(driver).move_to_element(element).perform()
            if not cls.cart_button_ready(driver, element):
                raise RuntimeError("Warenkorb-Button wurde während des Klicks gesperrt.")
            element.click()
        print("Klick gesendet. Warte auf die Antwort des IT-Shops ...", flush=True)
        try:
            result = WebDriverWait(
                driver, cls.CART_RESPONSE_TIMEOUT,
                ignored_exceptions=(StaleElementReferenceException,)
            ).until(lambda browser: cls.cart_action_response(browser, before_cart))
        except TimeoutException as error:
            diagnostic = cls.save_button_diagnostic(driver, "no_response_after_click")
            raise RuntimeError(
                "Der Button wurde angeklickt, aber der IT-Shop hat weder den Dialog "
                "'Hauptservice auswählen' geöffnet noch eine Warenkorb-Bestätigung angezeigt. "
                "Kein Erfolg gemeldet und kein zweiter Klick ausgeführt. "
                f"Button-Diagnose: {diagnostic}"
            ) from error
        cls.save_button_diagnostic(driver, "response_confirmed")
        print(result, flush=True)
        return result

    @classmethod
    def cart_button_ready(cls, driver, element):
        if not element.is_displayed() or not element.is_enabled():
            return False
        if "disabled" in (element.get_attribute("class") or "").split():
            return False
        if element.get_attribute("aria-disabled") == "true":
            return False
        return driver.execute_script(
            "return document.readyState === 'complete' && "
            "getComputedStyle(arguments[0]).pointerEvents !== 'none';", element
        )

    @classmethod
    def find_cart_button(cls, driver, depth=0):
        if depth == 0:
            driver.switch_to.default_content()
        candidates = [element for element in driver.find_elements(By.CSS_SELECTOR, cls.CART_BUTTON_SELECTOR)
                      if cls.cart_button_ready(driver, element)]
        if len(candidates) > 1:
            raise RuntimeError("Mehrere aktive grüne Warenkorb-Buttons gefunden; kein Klick ausgeführt.")
        if candidates:
            return candidates[0]
        if depth < 3:
            for frame in driver.find_elements(By.CSS_SELECTOR, "iframe, frame"):
                driver.switch_to.frame(frame)
                element = cls.find_cart_button(driver, depth + 1)
                if element:
                    return element
                driver.switch_to.parent_frame()
        return False

    @classmethod
    def cart_header_text(cls, driver):
        return " ".join(element.text.strip() for element in
                        driver.find_elements(By.CSS_SELECTOR, ".shop-cart-link")
                        if element.is_displayed())

    @classmethod
    def cart_action_response(cls, driver, before_cart):
        for heading in driver.find_elements(
            By.CSS_SELECTOR, "dialog[open] h2, [role='dialog'] h2, .modal.show h2"
        ):
            if heading.is_displayed() and "Hauptservice auswählen" in heading.text:
                return "IT-Shop-Klick bestätigt: 'Hauptservice auswählen' ist geöffnet. Bitte den Ziel-Rechner auswählen."
        for alert in driver.find_elements(By.CSS_SELECTOR, "[role='alert'], .alert, .toast"):
            if not alert.is_displayed():
                continue
            message = alert.text.strip()
            normalized = message.lower()
            if "warenkorb" in normalized and ("hinzugefügt" in normalized or "fehler" in normalized):
                if "nicht" in normalized or "fehler" in normalized:
                    raise RuntimeError(f"Der IT-Shop meldet: {message}")
                return f"Warenkorb-Bestätigung: {message}"
        after_cart = cls.cart_header_text(driver)
        if before_cart and after_cart and before_cart != after_cart:
            return f"IT-Shop-Klick bestätigt: Warenkorbanzeige geändert ({after_cart})."
        return False

    @classmethod
    def save_button_diagnostic(cls, driver, stage="state"):
        path = Runtime.data_root() / "itshop_button_diagnose.json"
        try:
            data = driver.execute_script(r"""
                return Array.from(document.querySelectorAll(
                    'button,a,[role="button"],input[type="button"],input[type="submit"]'
                )).filter(node => /warenkorb/i.test(
                    [node.textContent,node.value,node.getAttribute('aria-label')].join(' ')
                )).map(node => ({html: node.outerHTML.slice(0, 2500),
                    visible: !!(node.getBoundingClientRect().width
                        && node.getBoundingClientRect().height), disabled: !!node.disabled,
                    cssDisabled: node.classList.contains('disabled'),
                    pointerEvents: getComputedStyle(node).pointerEvents}));
            """)
            snapshot = {"stage": stage, "path": urlsplit(driver.current_url).path,
                        "readyState": driver.execute_script("return document.readyState"),
                        "buttons": data}
            history = []
            if stage != "before_wait" and path.exists():
                try:
                    history = json.loads(path.read_text(encoding="utf-8")).get("history", [])
                except (ValueError, OSError):
                    pass
            history.append(snapshot)
            path.write_text(json.dumps({**snapshot, "history": history[-8:]},
                ensure_ascii=False, indent=2), encoding="utf-8")
            return str(path)
        except (OSError, WebDriverException) as error:
            return f"Diagnose konnte nicht gespeichert werden: {error}"

    @classmethod
    def browser_worker(cls, driver_path, messages, closed):
        driver = None
        keep_browser_open = False
        try:
            messages.put(("status", "Edge wird gestartet ..."))
            driver = cls.create_browser(driver_path)
            print("Falls erforderlich: im Edge-Fenster mit dem eigenen Firmenkonto anmelden.")
            for url, status in (
                (cls.HOME_URL, "Startseite öffnen – bitte bei Bedarf anmelden ..."),
                (cls.WORKPLACE_URL, "Workplace wird geöffnet ..."),
                (cls.PRODUCT_URL, "InfoSim-Produktsuche wird geöffnet ..."),
            ):
                if closed.is_set():
                    return
                messages.put(("status", status))
                cls.open_page(driver, url)
                if url == cls.HOME_URL:
                    messages.put(("home_ready", "Home-Seite geladen. Weiter zum Workplace ..."))
                if url == cls.PRODUCT_URL:
                    messages.put(("product_ready", "Produktsuche erreicht. Fortschrittsfenster wird geschlossen."))
            if closed.is_set():
                return
            messages.put(("status", "Warte auf den InfoSim-Warenkorb-Button ..."))
            result = cls.click_add_to_cart(driver)
            keep_browser_open = True
            messages.put(("done", result))
        except Exception as error:
            keep_browser_open = True
            message = f"{type(error).__name__}: {error}"
            if driver is not None:
                message += f"\nButton-Diagnose: {cls.save_button_diagnostic(driver)}"
            print(f"IT-Shop-Automatisierung abgebrochen: {message}", file=sys.stderr)
            messages.put(("error", message))
        finally:
            if driver is not None:
                try:
                    if keep_browser_open:
                        driver.service.stop()
                    else:
                        driver.quit()
                except WebDriverException:
                    pass

    @classmethod
    def create_card(cls, title, description):
        if title == "Silver-Update vorhanden":
            import html
            reminder="Bitte laufende Silver-Simulationen vorher schließen."
            has_reminder=reminder in description
            description=description.replace(reminder,"").rstrip()
            dialog, footer, body = Dialogs.card(title, description)
            lines=[]
            for line in description.splitlines():
                formatted=html.escape(line)
                if line.startswith("Installiert"):
                    formatted='<span style="color:#f59e0b; font-size:14pt;">'+formatted+'</span>'
                elif line.startswith("Verfügbar"):
                    formatted='<span style="color:#22c55e; font-size:14pt;">'+formatted+'</span>'
                formatted=formatted.replace("Möchten Sie Silver aktualisieren?",'<span style="color:#facc15; font-size:16pt; font-weight:700;">Möchten Sie Silver aktualisieren?</span>')
                warning="Mit Ja wird zuerst die vorhandene Silver-Version deinstalliert"
                formatted=formatted.replace(warning,'<span style="color:#f59e0b; font-size:12pt;">'+warning+'</span>')
                lines.append(formatted)
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setText("<br>".join(lines))
            body.setStyleSheet("font:12pt 'Segoe UI';")
            if has_reminder:
                hint=QLabel(reminder)
                hint.setObjectName("silverSimulationReminder")
                hint.setWordWrap(True)
                hint.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
                hint.setStyleSheet("font:700 16pt 'Segoe UI'; padding:8px 0;")
                footer.addWidget(hint)
            dialog.resize(dialog.width(),min(500,dialog.maximumHeight()))
            return dialog,footer,body
        if title == "Wollen Sie Silver installieren?":
            dialog, footer, body = Dialogs.card(title, description)
            body.setStyleSheet("color:#facc15; font:700 18pt 'Segoe UI';")
            action = QLabel("wird installiert")
            action.setObjectName("silverInstallAction")
            action.setWordWrap(True)
            action.setStyleSheet("font:18pt 'Segoe UI';")
            message = body.parentWidget().layout()
            message.insertWidget(message.indexOf(body) + 1, action)
            return dialog, footer, body
        if title != cls.INFOSIM_QUESTION:
            return Dialogs.card(title, description)
        dialog, footer, body = Dialogs.card(title, cls.INFOSIM_DESCRIPTION)
        heading = dialog.findChild(QLabel, "heading")
        heading.setTextFormat(Qt.TextFormat.RichText)
        heading.setText('Haben Sie <span style="color:#facc15;">InfoSim</span> auf dem '
                        '<span style="color:#facc15;">Ziel-Rechner</span> installiert?')
        body.setStyleSheet("color:#40e0d0; font:12pt 'Segoe UI';")
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setText('<p>Wenn Sie InfoSim zum ersten Mal hören, dann brauchen Sie es definitiv :)</p>'
                     '<p><b>InfoSim ist ein Rechner-gebundener Dienst!</b></p>'
                     '<p style="color:#fca5a5;">Wenn Sie mit SiL auf einem anderen Rechner arbeiten wollen, kann die Installation notwendig sein.</p>')
        redirect = QLabel("mit Nein werden Sie zu IT-Shop weitergeleitet")
        redirect.setObjectName("itshopRedirect")
        redirect.setTextFormat(Qt.TextFormat.PlainText)
        redirect.setWordWrap(True)
        redirect.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        redirect.setStyleSheet("color:#f59e0b; font:700 14pt 'Segoe UI';")
        message = body.parentWidget().layout()
        message.insertWidget(message.count() - 1, redirect)
        dialog.resize(dialog.width(), min(500, dialog.maximumHeight()))
        return dialog, footer, body

    @classmethod
    def ask_question(cls, title, description):
        dialog, layout, _ = cls.create_card(title, description)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton("Abbrechen")
        cancel_button.setObjectName("cancelQuestion")
        cancel_button.setAutoDefault(False)
        cancel_button.clicked.connect(dialog.reject)
        no_button = QPushButton("Nein")
        if title == cls.INFOSIM_QUESTION:
            no_button.setStyleSheet("QPushButton {background:#dc2626; color:#ffffff; border:1px solid #ef4444;} QPushButton:hover {background:#ef4444; color:#ffffff;} QPushButton:pressed {background:#b91c1c; color:#ffffff;}")
        yes_button = QPushButton("Ja")
        yes_button.setObjectName("primary")
        if title == cls.INFOSIM_QUESTION:
            yes_button.setStyleSheet("QPushButton {background:#86efac; color:#172554; border:1px solid #86efac;} QPushButton:hover {background:#bbf7d0;} QPushButton:pressed {background:#4ade80;}")
        # Enter darf keine ungewollte Installation auslösen.
        for button in (no_button, yes_button):
            button.setAutoDefault(False)
        no_button.clicked.connect(lambda: dialog.done(2))
        yes_button.clicked.connect(dialog.accept)
        if title != "Silver-Update vorhanden":
            buttons.addWidget(cancel_button)
        else:
            cancel_button.deleteLater()
        buttons.addWidget(no_button)
        buttons.addWidget(yes_button)
        layout.addLayout(buttons)
        QTimer.singleShot(0, lambda: cls.foreground_dialog(dialog))
        result = dialog.exec()
        cls.QUESTION_CANCELLED = result == QDialog.DialogCode.Rejected
        return result == QDialog.DialogCode.Accepted

    @classmethod
    def show_message(cls, title, description):
        dialog, layout, _ = cls.create_card(title, description)
        close_button = QPushButton("Schließen")
        close_button.setObjectName("primary")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)
        QTimer.singleShot(0, lambda: cls.foreground_dialog(dialog))
        dialog.exec()

    @classmethod
    def create_progress_card(cls, title, description, button_label="Abbrechen"):
        dialog, layout, body = cls.create_card(title, description)
        if title == "Silver installieren":
            body.setStyleSheet("color:#f59e0b; font:14pt 'Segoe UI';")
        wait = QLabel("Bitte warten ...")
        wait.setObjectName("progressWait")
        wait.setStyleSheet("color:#facc15; font:700 16pt 'Segoe UI';")
        wait.setWordWrap(True)
        layout.addWidget(wait)
        track = QFrame()
        track.setObjectName("track")
        track.setFixedHeight(16)
        track.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(track)
        bar = QWidget(track)
        bar.setObjectName("movingBar")
        bar.setGeometry(0, 0, 110, 16)
        animation = QSequentialAnimationGroup(dialog)
        for start, end in ((0, 350), (350, 0)):
            part = QPropertyAnimation(bar, b"geometry", animation)
            part.setStartValue(QRect(start, 0, 110, 16))
            part.setEndValue(QRect(end, 0, 110, 16))
            part.setDuration(1100)
            part.setEasingCurve(QEasingCurve.Type.InOutSine)
            animation.addAnimation(part)
        animation.setLoopCount(-1)
        animation.currentAnimationChanged.connect(lambda current: cls.resize_animation(track, animation))
        cancel = QPushButton(button_label)
        cancel.clicked.connect(dialog.reject)
        layout.addWidget(cancel, alignment=Qt.AlignmentFlag.AlignRight)
        return dialog, body, animation

    @classmethod
    def resize_animation(cls, track, animation):
        width = max(20, track.width())
        segment = min(110, max(20, width // 4))
        for index in range(2):
            part = animation.animationAt(index)
            start, end = (0, width - segment) if index == 0 else (width - segment, 0)
            part.setStartValue(QRect(start, 0, segment, 16))
            part.setEndValue(QRect(end, 0, segment, 16))

    @classmethod
    def create_progress(cls, closed, app):
        dialog, body, animation = cls.create_progress_card(
            "InFoSim Bestellung", "Arbeitsplatz im IT-Shop wird automatisch geöffnet."
        )
        dialog.findChild(QLabel, "heading").setStyleSheet("font:700 22pt 'Segoe UI';")
        body.setStyleSheet("color:#40e0d0; font:14pt 'Segoe UI';")
        dialog.rejected.connect(lambda: cls.cancel_process(closed, app))
        return dialog, body, animation

    @classmethod
    def cancel_process(cls, closed, app):
        closed.set()
        app.quit()

    @classmethod
    def foreground_dialog(cls, dialog):
        dialog.showNormal()
        dialog.raise_()
        dialog.activateWindow()
        if os.name == "nt":
            SilverInstallation.show_wizard(int(dialog.winId()))

    @classmethod
    def itshop_notice(cls, description):
        dialog, layout, body = cls.create_card(
            "InfoSim auf dem Ziel-Rechner bestellen ...",
            "Wenn es vom IT-Shop angezeigt ist, wählen Sie den Ziel-Rechner und beenden Sie die Bestellung manuell"
        )
        body.setStyleSheet("color:#40e0d0; font:14pt 'Segoe UI';")
        hint = QLabel("Nach Abschluss Ihrer IT-Shop-Aktion rufen Sie dieses Fenster wieder auf. "
                      "Klicken Sie dann auf Weiter mit Silver-Installation, um fortzufahren.")
        hint.setWordWrap(True)
        font = hint.font()
        font.setBold(True)
        hint.setFont(font)
        hint.setStyleSheet("color:#facc15; font:700 14pt 'Segoe UI';")
        # Put the instruction in the scrollable message area, never above the footer.
        body.parentWidget().layout().addWidget(hint)
        next_button = QPushButton("Weiter mit Silver-Installation")
        next_button.setObjectName("primary")
        next_button.clicked.connect(dialog.accept)
        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(dialog.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(cancel)
        buttons.addWidget(next_button)
        layout.addLayout(buttons)
        QTimer.singleShot(0, lambda: cls.foreground_dialog(dialog))
        return dialog.exec() == QDialog.DialogCode.Accepted

    @classmethod
    def save_itshop_error(cls, message):
        report = {"process": "IT-Shop", "error": message}
        diagnostic = Runtime.data_root() / "itshop_button_diagnose.json"
        if "Button-Diagnose:" in message and diagnostic.is_file():
            try:
                report["button_diagnostic"] = json.loads(diagnostic.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        text = json.dumps(report, ensure_ascii=False, indent=2)
        path = Runtime.data_root() / "itshop_error.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", prefix="siLAssistent_ITShop_", delete=False) as stream:
                stream.write(text)
                path = Path(stream.name)
        return path

    @classmethod
    def open_itshop_log(cls, dialog, path):
        try:
            editor = Path(os.environ.get("WINDIR", "C:/Windows")) / "System32/notepad.exe"
            subprocess.Popen([str(editor), str(path)], shell=False)
        except OSError:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(dialog, "Logdatei öffnen", "Die Logdatei konnte nicht im Editor geöffnet werden.")

    @classmethod
    def show_itshop_error(cls, message):
        path = cls.save_itshop_error(message)
        dialog, footer, body = cls.create_card("IT-Shop-Aktion fehlgeschlagen",
            "Bei der IT-Shop-Aktion ist etwas schiefgelaufen.\n\n"
            "Bitte öffnen Sie die JSON-Logdatei und melden Sie deren Inhalt an den Support.")
        link = QLabel('<a href="itshop-log">JSON-Logdatei im Editor öffnen</a>')
        link.setObjectName("itshopLogLink")
        link.setTextFormat(Qt.TextFormat.RichText)
        link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse | Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
        link.setOpenExternalLinks(False)
        link.setWordWrap(True)
        link.linkActivated.connect(lambda _: cls.open_itshop_log(dialog, path))
        area = body.parentWidget().layout()
        area.insertWidget(area.indexOf(body) + 1, link)
        close = QPushButton("Schließen")
        close.setObjectName("primary")
        close.clicked.connect(dialog.accept)
        footer.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        QTimer.singleShot(0, lambda: cls.foreground_dialog(dialog))
        dialog.exec()

    @classmethod
    def finish_itshop(cls, app, state, silver_installer, message, successful):
        if not successful:
            state["exit_code"] = 1
            cls.show_itshop_error(message)
        else:
            if not cls.itshop_notice(message):
                state["exit_code"] = 0
                app.quit()
                return
            state["exit_code"] = SilverInstallation.run(
                cls, installer=silver_installer,
                description=message + "\n\nDie Installation auf dem Ziel-Rechner ist damit noch nicht bestätigt."
            )
        app.quit()

    @classmethod
    def update_progress(cls, app, progress, body, animation, timer,
                        messages, state, silver_installer):
        try:
            while True:
                kind, message = messages.get_nowait()
                print(message, flush=True)
                body.setToolTip(message)
                if kind == "home_ready":
                    state["home_ready"] = True
                    if state["show_progress"]:
                        progress.show()
                        progress.raise_()
                        animation.start()
                elif kind == "product_ready":
                    animation.stop()
                    # accept() schließt nur das Fenster und löst keinen Abbruch aus.
                    progress.accept()
                elif kind in ("done", "error"):
                    timer.stop()
                    animation.stop()
                    progress.accept()
                    QTimer.singleShot(0, lambda m=message, ok=(kind == "done"):
                        cls.finish_itshop(app, state, silver_installer, m, ok))
                    return
        except queue.Empty:
            pass

    @classmethod
    def run(cls, driver_path=None, show_progress=None, silver_installer=None):
        silver_installer = silver_installer or Config.state()["silverInstallerPath"]
        app = QApplication.instance() or QApplication(sys.argv[:1])
        app.setStyle("Fusion")
        app.setStyleSheet(cls.UI_STYLE)
        app.setQuitOnLastWindowClosed(False)
        if cls.ask_question(
            cls.INFOSIM_QUESTION,
            cls.INFOSIM_DESCRIPTION
        ):
            return SilverInstallation.run(
                cls, installer=silver_installer,
                description="InfoSim ist bereits installiert. Sie können jetzt die Silver-Installation starten."
            )
        # Ein mit X/Escape geschlossenes Dialogfenster soll ebenfalls beenden.
        # ask_question unterscheidet dafür unten zwischen Nein und Abbrechen.
        if cls.QUESTION_CANCELLED:
            return 0
        messages = queue.Queue()
        closed = threading.Event()
        state = {"exit_code": 1, "home_ready": False,
                 "show_progress": cls.SHOW_PROGRESS if show_progress is None else show_progress}
        progress, body, animation = cls.create_progress(closed, app)
        timer = QTimer()
        timer.setInterval(40)
        timer.timeout.connect(lambda: cls.update_progress(
            app, progress, body, animation, timer, messages, state, silver_installer
        ))
        worker = threading.Thread(
            target=cls.browser_worker, args=(driver_path, messages, closed), daemon=True
        )
        worker.start()
        timer.start()
        try:
            app.exec()
        finally:
            timer.stop()
            animation.stop()
            closed.set()
            worker.join()
        return state["exit_code"]

    @classmethod
    def browser_self_test(cls, result_file, driver_path=None):
        driver = None
        result = {"ok": False}
        try:
            options = webdriver.EdgeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-first-run")
            driver = cls.create_edge_driver(options, driver_path)
            driver.get("data:text/html,<title>SIL Browser Test</title><button id='test'>Test</button>")
            driver.find_element(By.ID, "test").click()
            assert driver.title == "SIL Browser Test"
            result = {"ok": True, "browser": driver.capabilities.get("browserVersion")}
        except Exception as error:
            result["error"] = f"{type(error).__name__}: {error}"
        finally:
            if driver is not None:
                driver.quit()
            Path(result_file).write_text(json.dumps(result), encoding="utf-8")
        return 0 if result["ok"] else 1

    @classmethod
    def launch_command(cls, silver_update=False, installer=None, previous_version=None, target_version=None, uninstall_target=None):
        command = ([sys.executable, "--sil-einrichten"]
                   if getattr(sys, "frozen", False) or "__compiled__" in globals()
                   else [sys.executable, str(Runtime.project_root() / "source/siLAssistent.py"), "--sil-einrichten"])
        if silver_update:
            command[-1] = "--silver-update"
            for flag, value in (("--silver-installer", installer), ("--silver-previous-version", previous_version),
                                ("--silver-target-version", target_version), ("--silver-uninstall-target", uninstall_target)):
                if value:
                    command.extend([flag, value])
        return command

    @classmethod
    def launch(cls, silver_update=False, installer=None, previous_version=None, target_version=None, uninstall_target=None):
        if getattr(cls, "_process", None) is not None and cls._process.poll() is None:
            if silver_update:
                raise RuntimeError("SiL-Einrichten läuft bereits. Bitte zuerst den laufenden Vorgang beenden.")
            return cls._process
        command=cls.launch_command(silver_update,installer,previous_version,target_version,uninstall_target)
        with (Runtime.data_root() / "silEinrichten.log").open("a", encoding="utf-8") as log:
            cls._process = subprocess.Popen(command, cwd=str(Runtime.project_root()),
                                            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        return cls._process

    @classmethod
    def run_silver_update(cls, installer=None, previous_version=None, target_version=None, uninstall_target=None):
        app = QApplication.instance() or QApplication(sys.argv[:1])
        app.setStyle("Fusion")
        app.setStyleSheet(cls.UI_STYLE)
        app.setQuitOnLastWindowClosed(False)
        SilverInstallation.configure_update(True, previous_version, target_version, uninstall_target)
        return SilverInstallation.install(cls, installer)

    @classmethod
    def main(cls):
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--driver-path", help="Optionaler Pfad zu msedgedriver.exe.")
        parser.add_argument("--silver-installer", help="Optionaler Pfad zum Silver-Installer (.exe/.msi).")
        parser.add_argument("--progress", action=argparse.BooleanOptionalAction, default=None,
                            help="Fortschrittsfenster aktivieren/deaktivieren (standardmäßig aktiv).")
        parser.add_argument("--Assistent-Worker-result", "--silver-worker-result", dest="silver_worker_result", help=argparse.SUPPRESS)
        parser.add_argument("--browser-self-test-result", help=argparse.SUPPRESS)
        parser.add_argument("--silver-update", action="store_true", help=argparse.SUPPRESS)
        parser.add_argument("--silver-target-version", help=argparse.SUPPRESS)
        parser.add_argument("--silver-previous-version", help=argparse.SUPPRESS)
        parser.add_argument("--silver-uninstall-target", help=argparse.SUPPRESS)
        args = parser.parse_args()
        SilverInstallation.configure_update(args.silver_update, args.silver_previous_version,
                                            args.silver_target_version, args.silver_uninstall_target)
        if args.browser_self_test_result:
            return cls.browser_self_test(args.browser_self_test_result, args.driver_path)
        if args.silver_worker_result:
            return SilverInstallation.helper_main(
                args.silver_worker_result, args.silver_installer or SilverInstallation.INSTALLER_PATH
            )
        if args.silver_update:
            return cls.run_silver_update(args.silver_installer, args.silver_previous_version,
                                         args.silver_target_version, args.silver_uninstall_target)
        return cls.run(driver_path=args.driver_path, show_progress=args.progress,
                       silver_installer=args.silver_installer)


if __name__ == "__main__":
    sys.exit(SilEinrichten.main())
