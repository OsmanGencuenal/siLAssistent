"""Profillose Silver-Silent-Installation; Setup-IDs aus Silver 2026.03-1."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import time
import winreg
from .licences import SilverLicences
from .updates import SilverUpdates
from ..core.config import Config
from ..core.errors import AssistantError
from ..core.runtime import Runtime


class SilverSilent:
    # Explicit values, never loaded from a saved installation/profile.
    COMPONENTS = ("main", r"main\utility_modules", r"main\export_tools", r"main\demos")
    TASKS = ("user_setup", "silver_home", "path", "mingw_path", "matlab_path",
             "sil_assoc", "icons", r"icons\desktop", r"icons\startmenu")

    @classmethod
    def request(cls, sid=None):
        return {"sid": sid or SilverUpdates.user_sid(),
                "local_app_data": str(Path(os.environ["LOCALAPPDATA"]).resolve()),
                "ini_path": str(Config.path().resolve())}

    @classmethod
    def validate_request(cls, request):
        import re
        sid = request.get("sid", "")
        if not re.fullmatch(r"S-1-[0-9-]+", sid):
            raise AssistantError("Windows-Benutzerkennung im Silver-Auftrag fehlt.")
        local = Path(request["local_app_data"])
        ini = Path(request["ini_path"])
        if not local.is_absolute() or str(local).startswith("\\\\") or not ini.is_absolute():
            raise AssistantError("Der Silver-Auftrag benötigt lokale Benutzerpfade und einen vollständigen INI-Pfad.")
        # Fail before uninstalling if the original user hive cannot be accessed.
        with winreg.OpenKey(winreg.HKEY_USERS, sid + r"\Environment", 0,
                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE):
            pass
        return request

    @classmethod
    def command(cls, installer, version, request, log):
        if not SilverUpdates.version_label(version):
            raise AssistantError("Silver-Zielversion für Silent fehlt.")
        demos = Path(request["local_app_data"]) / f"Silver {version} Examples"
        return [str(installer), "/VERYSILENT", "/ACCEPTLICENSES", "/SUPPRESSMSGBOXES",
                "/SP-", "/NORESTART", "/RESTARTEXITCODE=3010", "/NOCLOSEAPPLICATIONS",
                "/NORESTARTAPPLICATIONS", "/TYPE=full", "/TASKS=" + ",".join(cls.TASKS),
                "/DEMOFOLDER=" + str(demos), "/LOG=" + str(log)]

    @classmethod
    def environment(cls):
        env = os.environ.copy()
        env.update(SNPSLMD_LICENSE_FILE=SilverLicences.environment_value(), SNPS_QUEUE="1", FLEXLM_BATCH="0")
        return env

    @classmethod
    def merged_path(cls, existing):
        wanted = (r"%SILVER_HOME%\common\ext-tools\mingw\bin", r"%SILVER_HOME%\bin")
        result = list(wanted)
        seen = {item.casefold().rstrip("\\") for item in wanted}
        for item in existing.split(";"):
            if item and item.casefold().rstrip("\\") not in seen:
                result.append(item)
                seen.add(item.casefold().rstrip("\\"))
        return ";".join(result)

    @classmethod
    def configure_user(cls, request, home):
        with winreg.OpenKey(winreg.HKEY_USERS, request["sid"] + r"\Environment", 0,
                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
            try:
                old_path = winreg.QueryValueEx(key, "Path")[0]
            except FileNotFoundError:
                old_path = ""
            values = {"SILVER_HOME": str(home), "SNPSLMD_LICENSE_FILE": SilverLicences.environment_value(),
                      "SNPS_QUEUE": "1", "FLEXLM_BATCH": "0", "Path": cls.merged_path(old_path)}
            for name, value in values.items():
                winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ if name == "Path" else winreg.REG_SZ, value)
            for name, expected in values.items():
                if winreg.QueryValueEx(key, name)[0] != expected:
                    raise AssistantError(f"Silver-Benutzereinstellung konnte nicht bestätigt werden: {name}")
        # Notify Explorer and newly started applications about the environment.
        from ctypes import wintypes
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                           wintypes.LPCWSTR, wintypes.UINT, wintypes.UINT,
                                           ctypes.POINTER(ctypes.c_size_t)]
        output = ctypes.c_size_t()
        user.SendMessageTimeoutW(0xffff, 0x1a, 0, "Environment", 0x2, 3000, ctypes.byref(output))

    @classmethod
    def verify_installation(cls, version):
        entries = [e for e in SilverUpdates.installed() if SilverUpdates.release_matches(e["version"], version)]
        if not entries:
            raise AssistantError("Silent-Setup beendet, aber die Silver-Zielversion ist nicht registriert.")
        entry = entries[0]
        home = Path(entry["InstallLocation"])
        if not (home / "bin" / "Silver.exe").is_file():
            raise AssistantError("Die installierte Silver.exe wurde nicht gefunden.")
        scope, sid, view, name = entry["locator"].split("|", 3)
        hive = winreg.HKEY_LOCAL_MACHINE if scope == "machine" else winreg.HKEY_USERS
        prefix = "" if scope == "machine" else sid + "\\"
        flag = winreg.KEY_WOW64_64KEY if view == "64" else winreg.KEY_WOW64_32KEY
        with winreg.OpenKey(hive, prefix + SilverUpdates.UNINSTALL_ROOT + "\\" + name, 0, winreg.KEY_READ | flag) as key:
            components = set(winreg.QueryValueEx(key, "Inno Setup: Selected Components")[0].split(","))
            tasks = set(winreg.QueryValueEx(key, "Inno Setup: Selected Tasks")[0].split(","))
        missing = set(cls.COMPONENTS) - components | set(cls.TASKS) - tasks
        if missing or any(t == "system_setup" or t == "xil" or t.startswith("xil\\") for t in tasks):
            raise AssistantError("Silver-Setupoptionen nicht vollständig bestätigt: " + ", ".join(sorted(missing or tasks)))
        return home

    @classmethod
    def log_has_started(cls, log):
        # A notification only. Success is established by process exit and registry/file verification.
        try:
            raw = Path(log).read_bytes()[:131072]
        except OSError:
            return False
        encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        return "Starting the installation process." in raw.decode(encoding, errors="replace")

    @classmethod
    def run(cls, installer, version, request, messages, cancelled, known_pids, record):
        cls.validate_request(request)
        # Validate embedded licence configuration before launching the installer.
        env = cls.environment()
        log_root = Path(request["local_app_data"]) / "siLAssistent"
        log_root.mkdir(parents=True, exist_ok=True)
        log = log_root / ("silver_silent_" + str(time.time_ns()) + ".log")
        command = cls.command(installer, version, request, log)
        record("silent_launch_requested", command=command, log=str(log), user_sid=request["sid"])
        process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        known_pids.add(process.pid)
        record("silent_process_started", pid=process.pid)
        started = False
        deadline = time.monotonic() + 7200
        while process.poll() is None:
            if cancelled.is_set():
                raise AssistantError("Silver-Installation abgebrochen.")
            if time.monotonic() >= deadline:
                raise AssistantError("Silver-Silent-Installation antwortet seit zwei Stunden nicht. Protokoll: " + str(log))
            if not started and cls.log_has_started(log):
                started = True
                messages.put(("installation_started", "Silver wird im Hintergrund installiert. Der Assistent wird geschlossen."))
                record("installation_started", mode="silent")
            cancelled.wait(0.3)
        if cancelled.is_set():
            raise AssistantError("Silver-Installation abgebrochen.")
        if process.returncode not in (0, 3010):
            raise AssistantError(f"Silver-Silent-Setup wurde mit Fehlercode {process.returncode} beendet. Protokoll: {log}")
        home = cls.verify_installation(version)
        cls.configure_user(request, home)
        record("silent_configuration_verified", home=str(home), reboot_required=process.returncode == 3010,
               licence_servers=SilverLicences.environment_value(), queuing=True)
        return request["ini_path"]
