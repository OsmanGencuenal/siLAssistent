"""Read-only share check; launch a locally staged, verified update installer."""
from .network_share import NetworkShare
from pathlib import Path
import configparser
import hashlib
import os
import re
import shutil
import tempfile
import stat
from .errors import AssistantError

class UpdateCancelled(AssistantError):
    pass

class UpdateManager:
    @classmethod
    def version_tuple(cls, text):
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", text.strip()):
            raise ValueError(f"Invalid release version: {text}")
        parts = tuple(map(int, text.strip().split(".")))
        return parts + (0,) * (4 - len(parts))

    @classmethod
    def check(cls, ini_path, installed):
        if not ini_path:
            return {"available": False, "configured": False}
        parser = configparser.ConfigParser(interpolation=None)
        path = Path(ini_path)
        raw = NetworkShare.read_bytes(path)
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        parser.read_string(text)
        from .config import Config
        Config.initialize_setup_counter(parser)
        Config.sync_update_paths(parser)
        Config.sync_support_mail(parser)
        section = parser["UPDATE"]
        latest = section["latest_version"].strip()
        installer = Config.network_path(section.get("installer_path", "").strip())
        if installer and not Path(installer).is_absolute():
            installer = str(path.parent / installer)
        return {"available": cls.version_tuple(latest) > cls.version_tuple(installed),
                "configured": True, "latest_version": latest, "installer_path": installer,
                "force_update": section.getboolean("force_update", fallback=False),
                "message": section.get("message", "Neue Version verfügbar."),
                "sha256": section.get("sha256", "").strip().lower()}

    @classmethod
    def stage(cls, release, directory=None, progress=None, cancelled=None):
        cls.check_cancelled(cancelled)
        if progress:progress("Update ... Verbindung zum Laufwerk wird hergestellt …",None)
        source = Path(release["installer_path"])
        with NetworkShare.access(source):metadata=source.stat()
        if not stat.S_ISREG(metadata.st_mode) or source.suffix.lower() != ".exe":
            raise AssistantError(f"Update installer not found: {source}")
        digest = release.get("sha256", "")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise AssistantError("Release INI must contain the installer's SHA-256 before installation.")
        if progress:progress("Update ... Installer wird vorbereitet …",None)
        directory = Path(directory or tempfile.mkdtemp(prefix="siLAssistent_update_"))
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "siLAssistent_Installer.exe"
        if source.resolve() == target.resolve():
            raise AssistantError("Update staging target must differ from the release source.")
        temporary = target.with_suffix(".partial")
        try:
            total=metadata.st_size;copied=0
            if progress:progress("Update ... Installer wird vom Laufwerk angefordert …",None)
            cls.check_cancelled(cancelled)
            with temporary.open("wb") as outgoing:
                for chunk in NetworkShare.chunks(source):
                    cls.check_cancelled(cancelled)
                    outgoing.write(chunk);copied+=len(chunk)
                    if progress:progress(f"Update ... {copied/1048576:.1f} von {total/1048576:.1f} MB übertragen",round(80*copied/max(total,1),1))
                if progress:progress("Update ... Lokale Datei wird fertig gespeichert …",None)
                outgoing.flush();os.fsync(outgoing.fileno())
            checksum=hashlib.sha256();verified=0
            with temporary.open("rb") as stream:
                while chunk:=stream.read(1024*1024):
                    cls.check_cancelled(cancelled)
                    checksum.update(chunk);verified+=len(chunk)
                    if progress:progress("Installer-Prüfsumme wird geprüft …",round(80+20*verified/max(total,1),1))
            calculated=checksum.hexdigest()
            if calculated != digest:
                raise AssistantError("Update installer checksum mismatch")
            cls.check_cancelled(cancelled)
            os.replace(temporary, target)
            if progress:progress("Update ist vorbereitet und geprüft.",100)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    @classmethod
    def launch(cls, installer, launcher=None, foreground=False):
        path = Path(installer).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        if launcher is not None:
            launcher(str(path))
        elif os.name == "nt":
            if foreground:
                from .installer_foreground import InstallerForeground
                return InstallerForeground.launch(path)
            os.startfile(str(path))
        else:
            raise AssistantError("Windows installer launch requires Windows")

    @classmethod
    def launch_after_exit(cls,installer):
        import subprocess,sys,psutil
        from .runtime import Runtime
        target=Path(installer).resolve()
        if not target.is_file():raise FileNotFoundError(target)
        command=[sys.executable]
        if not Runtime.is_compiled():command.append(str(Runtime.project_root()/"source/siLAssistent.py"))
        command += ["--apply-update",str(target),"--wait-for-pid",str(os.getpid()),"--wait-for-created",str(psutil.Process().create_time())]
        log=Runtime.log_root()/"update_install.log"
        with log.open("a",encoding="utf-8") as stream:
            worker=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        from .installer_foreground import InstallerForeground
        InstallerForeground.allow(worker.pid)
        return worker

    @classmethod
    def apply_after_exit(cls,installer,pid,created):
        import psutil
        try:
            parent=psutil.Process(pid)
            if parent.create_time()==created:parent.wait(timeout=120)
        except psutil.NoSuchProcess:pass
        except psutil.TimeoutExpired as error:
            raise AssistantError("Die bisherige Anwendung wurde nicht beendet; das Update wurde nicht gestartet.") from error
        cls.launch(installer,foreground=True)
        return 0

    @classmethod
    def write_manifest(cls, path, version, installer, sha256):
        from .config import Config
        cls.version_tuple(version)
        if not re.fullmatch(r"[a-fA-F0-9]{64}", sha256):
            raise AssistantError("Ungültige Installer-Prüfsumme für die Veröffentlichung.")
        path = Path(path)
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        if path.exists():
            raw = NetworkShare.read_bytes(path)
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("cp1252")
            parser.read_string(text)
        if not parser.has_section("UPDATE"):
            parser.add_section("UPDATE")
        section = parser["UPDATE"]
        from .release_paths import ReleasePaths
        if not parser.has_section("PATH"):parser.add_section("PATH")
        for key in ReleasePaths.KEYS:
            existing_path=next((value for name,value in parser["PATH"].items() if name.casefold()==key.casefold()),None)
            previous=next((value for name,value in section.items() if name.casefold()==key.casefold()),Config.STATE_DEFAULTS[key])
            for name in list(section):
                if name.casefold()==key.casefold():del section[name]
            for name in list(parser["PATH"]):
                if name.casefold()==key.casefold():del parser["PATH"][name]
            parser["PATH"][key]=existing_path if existing_path is not None else previous
        values = {"latest_version": version, "installer_path": str(installer), "force_update": "0",
                  "message": "Neue siLAssistent-Version verfügbar.", "sha256": sha256.lower()}
        for key, value in values.items():
            for existing in list(section):
                if existing.casefold() == key.casefold():
                    del section[existing]
            section[key] = value
        path.parent.mkdir(parents=True, exist_ok=True)
        Config.write(path, parser)

    @classmethod
    def check_cancelled(cls,cancelled):
        if cancelled is not None and cancelled.is_set():
            raise UpdateCancelled("Manuelle Installation gewählt. Automatisches Update abgebrochen.")
