"""Silver release checks and consent-driven replacement using registered uninstallers."""
from ..core.network_share import NetworkShare
from pathlib import Path
import configparser
import ctypes
from ctypes import wintypes
import os
import re
import subprocess
import time
import winreg
from ..core.config import Config
from ..core.errors import AssistantError

class SilverUpdates:
    UNINSTALL_ROOT = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"

    @classmethod
    def version_label(cls, text):
        match = re.search(r"([A-Z]-\d{4}\.\d{2}(?:[.-]\d+)*)", str(text), re.I)
        return match.group(1).upper() if match else None

    @classmethod
    def family(cls, text):
        label = cls.version_label(text)
        match = re.match(r"([A-Z]-\d{4}\.\d{2})", label or "")
        return match.group(1) if match else None

    @classmethod
    def release(cls, ini_path=None):
        path = Path(ini_path or Config.load()["update_ini_path"])
        parser = configparser.ConfigParser(interpolation=None)
        raw = NetworkShare.read_bytes(path)
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252")
        parser.read_string(text)
        installer = parser.get("PATH", "silverInstallerPath", fallback=parser.get("UPDATE", "silverInstallerPath", fallback="")).strip()
        if not installer:
            raise AssistantError(f"silverInstallerPath fehlt in der Laufwerk-INI: {path}")
        target = Path(installer)
        if not target.is_absolute():
            target = path.parent / target
        version = cls.version_label(target.name)
        if target.suffix.lower() != ".exe" or version is None:
            raise AssistantError("silverInstallerPath muss einen versionierten SilverSetup-Installer (.exe) bezeichnen.")
        return {"installer_path": str(target), "version": version, "ini_path": str(path)}

    @classmethod
    def sync_path(cls, release):
        Config.set_state("silverInstallerPath", release["installer_path"])

    @classmethod
    def user_sid(cls):
        import win32api, win32security, win32con
        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
        try:
            return win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, win32security.TokenUser)[0])
        finally:
            token.Close()

    @classmethod
    def registered_entry(cls, locator):
        parts = locator.split("|", 3)
        if len(parts) != 4:
            raise AssistantError("Ungültige Silver-Deinstallationskennung.")
        scope, sid, view, name = parts
        if "\\" in name or "/" in name or not name:
            raise AssistantError("Ungültiger Silver-Registrierungsschlüssel.")
        if view not in ("32", "64"):
            raise AssistantError("Ungültige Registry-Ansicht.")
        flags = winreg.KEY_WOW64_64KEY if view == "64" else winreg.KEY_WOW64_32KEY
        if scope == "machine" and sid == "-":
            hive = winreg.HKEY_LOCAL_MACHINE
            key_path = cls.UNINSTALL_ROOT + "\\" + name
        elif scope == "user" and re.fullmatch(r"S-1-[0-9-]+", sid):
            hive = winreg.HKEY_USERS
            key_path = sid + "\\" + cls.UNINSTALL_ROOT + "\\" + name
        else:
            raise AssistantError("Ungültiger Silver-Registry-Bereich.")
        try:
            with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | flags) as key:
                values = {}
                for field in ("DisplayName", "DisplayVersion", "Publisher", "InstallLocation", "UninstallString"):
                    try:
                        values[field] = winreg.QueryValueEx(key, field)[0]
                    except FileNotFoundError:
                        values[field] = ""
        except FileNotFoundError:
            return None
        if not re.match(r"^Silver\s+[A-Z]-\d{4}\.\d{2}", values["DisplayName"], re.I):
            raise AssistantError("Der Registrierungsschlüssel gehört nicht zu einer Silver-Installation.")
        if values["Publisher"] and not any(name in values["Publisher"].casefold() for name in ("synopsys", "qtronic")):
            raise AssistantError("Unerwarteter Herausgeber der Silver-Installation.")
        values.update(locator=locator, version=cls.version_label(values["DisplayName"]) or cls.version_label(values["DisplayVersion"]))
        return values

    @classmethod
    def installed(cls):
        entries = []
        sid = cls.user_sid()
        for hive, scope, owner in ((winreg.HKEY_LOCAL_MACHINE, "machine", "-"), (winreg.HKEY_CURRENT_USER, "user", sid)):
            for view, flag in (("64", winreg.KEY_WOW64_64KEY), ("32", winreg.KEY_WOW64_32KEY)):
                try:
                    with winreg.OpenKey(hive, cls.UNINSTALL_ROOT, 0, winreg.KEY_READ | flag) as root:
                        names = [winreg.EnumKey(root, i) for i in range(winreg.QueryInfoKey(root)[0])]
                except FileNotFoundError:
                    continue
                for name in names:
                    locator = "|".join((scope, owner, view, name))
                    try:
                        entry = cls.registered_entry(locator)
                    except (AssistantError, PermissionError):
                        continue
                    if entry is not None and not any(existing["UninstallString"] == entry["UninstallString"] for existing in entries):
                        entries.append(entry)
        return entries

    @classmethod
    def select_installed(cls, entries, recorded=None):
        if not entries:
            return None
        if recorded:
            same = [entry for entry in entries if cls.family(entry["version"]) == cls.family(recorded)]
            if len(same) == 1:
                return same[0]
        if len(entries) == 1:
            return entries[0]
        raise AssistantError("Mehrere Silver-Versionen sind installiert. Die aktive Version muss zuerst eindeutig festgelegt werden.")

    @classmethod
    def release_matches(cls, installed, offered):
        # Registry names may append the build date, e.g. -1.260409.
        installed=cls.version_label(installed)
        offered=cls.version_label(offered)
        return bool(installed and offered and (installed==offered or installed.startswith(offered+".")))

    @classmethod
    def installed_files(cls):
        import win32api
        roots={Path(value)/"Synopsys" for key in ("ProgramFiles","ProgramW6432","ProgramFiles(x86)") if (value:=os.environ.get(key))}
        candidates=set()
        for root in roots:
            if root.is_dir():
                candidates.update(root.glob("Silver */bin/Silver.exe"))
        home=Config.load().get("silver_home") or os.environ.get("SILVER_HOME")
        if home:
            candidates.add(Path(home)/"bin"/"Silver.exe")
        versions=[]
        for executable in candidates:
            # Never treat a remote machine's installation as local.
            if str(executable).startswith(("\\\\","//")):
                continue
            try:
                translations=win32api.GetFileVersionInfo(str(executable),"\\VarFileInfo\\Translation")
                for language,codepage in translations:
                    version=win32api.GetFileVersionInfo(str(executable),f"\\StringFileInfo\\{language:04x}{codepage:04x}\\ProductVersion")
                    label=cls.version_label(version)
                    if label:
                        versions.append({"version":label,"path":str(executable)})
                        break
            except (OSError,win32api.error):
                continue
        return versions

    @classmethod
    def save_version_diagnostic(cls, release, state, entries, files):
        import json
        import socket
        from ..core.runtime import Runtime
        data={"computer":socket.gethostname(),"ini_path":str(Config.path()),
              "recorded_version":state["InstalledSilverVersion"],"offered_version":release["version"],
              "registered_installations":entries,"local_executables":files}
        try:
            (Runtime.log_root()/"silver_version_diagnose.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        except OSError:
            pass

    @classmethod
    def refresh_local_version(cls, state_ini_path=None):
        entries = cls.installed()
        files = cls.installed_files()
        candidates = entries + files
        # The newest locally detected installation is independent of a cached None/old value.
        entry = max(candidates, key=lambda e: tuple(int(v) for v in re.findall(r"\d+", e["version"]))) if candidates else None
        installed = entry["version"] if entry else None
        if state_ini_path is None:
            Config.set_state("InstalledSilverVersion", installed)
        else:
            Config.set_state("InstalledSilverVersion", installed, path=Path(state_ini_path))
        return installed

    @classmethod
    def check(cls, ini_path=None):
        try:
            release = cls.release(ini_path)
        except Exception:
            cls.refresh_local_version()
            raise
        cls.sync_path(release)
        state = Config.state()
        entries=cls.installed()
        files=cls.installed_files()
        cls.save_version_diagnostic(release,state,entries,files)
        matching=[entry for entry in entries if cls.release_matches(entry["version"],release["version"])]
        file_matches=[entry for entry in files if cls.release_matches(entry["version"],release["version"])]
        if matching or file_matches:
            installed=(matching or file_matches)[0]["version"]
            if state["InstalledSilverVersion"]!=installed:
                Config.set_state("InstalledSilverVersion",installed)
            return {**release,"available":False,"installed_version":installed,"target_locator":matching[0]["locator"] if matching else None}
        entry = cls.select_installed(entries, state["InstalledSilverVersion"])
        if entry is None:
            return {**release, "available": False, "installed_version": None, "target_locator": None}
        recorded = state["InstalledSilverVersion"]
        installed = entry["version"]
        if installed != recorded:
            Config.set_state("InstalledSilverVersion", installed)
        return {**release, "available": not cls.release_matches(installed, release["version"]),
                "installed_version": installed, "target_locator": entry["locator"]}

    @classmethod
    def split_command(cls, text):
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        count = ctypes.c_int()
        pointer = shell.CommandLineToArgvW(text, ctypes.byref(count))
        if not pointer:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return [pointer[index] for index in range(count.value)]
        finally:
            kernel.LocalFree(pointer)

    @classmethod
    def validate_installer(cls, path):
        path = Path(path)
        if not path.is_file() or path.suffix.lower() != ".exe":
            raise AssistantError("Der neue Silver-Installer ist lokal nicht verfügbar.")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetBinaryTypeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetBinaryTypeW.restype = wintypes.BOOL
        binary_type = wintypes.DWORD()
        if not kernel.GetBinaryTypeW(str(path), ctypes.byref(binary_type)) or binary_type.value not in (0, 6):
            raise AssistantError("Die lokale Silver-Installerkopie ist keine gültige Windows-Anwendung. Alte Installation bleibt erhalten.")

    @classmethod
    def uninstall_command(cls, entry):
        command = cls.split_command(entry["UninstallString"])
        if not command:
            raise AssistantError("Kein Silver-Deinstallationsprogramm registriert.")
        executable = Path(command[0]).resolve()
        location = Path(entry["InstallLocation"]).resolve() if entry["InstallLocation"] else None
        if (location is None or not executable.is_relative_to(location) or
            not re.fullmatch(r"unins\d+\.exe", executable.name, re.I) or not executable.is_file()):
            raise AssistantError("Kein gültiger registrierter Inno-Silver-Uninstaller gefunden.")
        # /SILENT retains the uninstall progress window; /NORESTART prevents a reboot.
        return [str(executable), "/SILENT", "/NORESTART"]

    @classmethod
    def ensure_not_running(cls, entry):
        import psutil
        location = Path(entry["InstallLocation"]).resolve()
        for process in psutil.process_iter(["name", "exe"]):
            if str(process.info.get("name") or "").casefold() not in ("silver.exe", "silver2.exe", "silver3.exe", "silversim.exe", "silversim2.exe", "silversim3.exe"):
                continue
            executable = process.info.get("exe")
            if not executable or Path(executable).resolve().is_relative_to(location):
                raise AssistantError("Bitte die laufende Silver-Simulation schließen, bevor das Update gestartet wird.")

    @classmethod
    def uninstall(cls, locator, previous_version, messages, cancelled, stop_process=None):
        if not locator or not previous_version:
            raise AssistantError("Die vom Benutzer bestätigte Silver-Version ist nicht eindeutig angegeben.")
        entry = cls.registered_entry(locator)
        if entry is None:
            raise AssistantError("Die bestätigte Silver-Installation ist nicht mehr registriert. Bitte neu prüfen.")
        if cls.family(entry["version"]) != cls.family(previous_version):
            raise AssistantError("Die installierte Silver-Version hat sich seit der Bestätigung geändert.")
        cls.ensure_not_running(entry)
        command = cls.uninstall_command(entry)
        if cancelled.is_set():
            raise AssistantError("Silver-Update abgebrochen.")
        messages.put(("status", f"Silver {previous_version} wird zuerst deinstalliert ..."))
        process = subprocess.Popen(command, shell=False)
        while process.poll() is None:
            if cancelled.wait(0.2):
                if stop_process is not None:
                    stop_process({process.pid})
                else:
                    process.terminate()
                    process.wait(timeout=15)
                raise AssistantError("Silver-Deinstallation abgebrochen. Neue Installation wird nicht gestartet.")
        if process.returncode != 0:
            raise AssistantError(f"Silver-Deinstallation fehlgeschlagen (Exitcode {process.returncode}). Neue Installation wird nicht gestartet.")
        deadline = time.monotonic() + 20
        while cls.registered_entry(locator) is not None:
            if time.monotonic() >= deadline or cancelled.wait(0.2):
                raise AssistantError("Alte Silver-Installation weiterhin registriert. Neue Installation wird nicht gestartet.")
        Config.set_state("InstalledSilverVersion", None)
        messages.put(("status", "Alte Silver-Version entfernt. Die neue Installation wird jetzt gestartet ..."))

    @classmethod
    def record_success(cls, version, ini_path=None):
        if not version:
            raise AssistantError("Silver-Zielversion fehlt im Installationsauftrag.")
        entries = [entry for entry in cls.installed() if cls.release_matches(entry["version"], version)]
        if not entries:
            raise AssistantError("Silver meldet Abschluss, aber die genaue Zielversion ist noch nicht als installiert registriert.")
        installed = entries[0]["version"]
        if ini_path is None:
            Config.set_state("InstalledSilverVersion", installed)
        else:
            Config.set_state("InstalledSilverVersion", installed, path=Path(ini_path))
        return installed
