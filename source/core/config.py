import configparser
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from .runtime import Runtime
from . import build_settings

class Config:
    UPDATE_INI = r"\\53.55.34.240\me7work$\Projekte\M286\04_Software_EDL\30_SiL\004_Tools\ini\siLAssistent_Update.ini"
    LEGACY_UPDATE_INI = r"\\53.55.34.240\me7work$\Projekte\M286\04_Software_EDL\30_SiL\004_Tools\siLAssistent_Update.ini"
    STATE_SECTION = "STATE"
    USER_SECTION = "USER"
    PATH_SECTION = "PATH"
    PATH_KEYS = frozenset(("InstalledSilverVersion","GitSetupRepo","silverInstallerPath","GitLocalRepoPath","GitInstallationPath","DriveSetupLocalPath","silSetupPath","DcmEditorPath"))
    USER_KEYS = frozenset(("GitUserState", "JiraUserState", "GitUserLicenceState"))
    STATE_DEFAULTS = {
        "DcmEditorPath": "",
        "SetupAutoConnect": "False",
        "SetupHeadless": "False",
        "SetupExitNow": "False",
        "FlashFilesGrouped": "False",
        "silSetupPath": '\\\\53.55.34.240\\me7work$\\Projekte\\M286\\04_Software_EDL\\30_SiL\\000_SiL_Setup\\SimFiles',
        "silSetupVersionCounter": "0",
        "DriveSetupLocalPath": "",
        "GitUserLicenceState": "False",
        "GitUserState": "False",
        "JiraUserState": "False",
        "GitInstallationState": "False",
        "InstalledSilverVersion": "",
        "GitLocalRepoPath": "",
        "GitInstallationPath": r"\\53.55.34.240\me7work$\Projekte\M286\04_Software_EDL\30_SiL\Silver_Software\_tools\Git-2.56.0.4-64-bit.exe",
        "GitSetupRepo": "https://mercedes-benz.ghe.com/devM286/SimFiles.git",
        "silverInstallerPath": r"\\53.55.34.240\me7work$\Projekte\M286\04_Software_EDL\30_SiL\Silver_Software\SilverSetup_Y-2026.03-1.exe",
    }
    STATE_DEFAULTS.update(build_settings.RELEASE_PATHS)
    BOOLEAN_STATES = frozenset(("GitUserLicenceState", "GitUserState", "JiraUserState", "GitInstallationState", "SetupAutoConnect", "SetupHeadless", "SetupExitNow", "FlashFilesGrouped"))

    @classmethod
    def section_for(cls, key):
        return cls.USER_SECTION if key in cls.USER_KEYS else cls.PATH_SECTION if key in cls.PATH_KEYS else cls.STATE_SECTION

    @classmethod
    def path(cls):
        return Runtime.project_root() / "siLAssistent.ini"

    @classmethod
    def parser(cls, path):
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        if path.exists():
            parser.read_string(path.read_text(encoding="utf-8-sig"))
        return parser

    @classmethod
    @contextmanager
    def locked(cls, path):
        import msvcrt
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_suffix(path.suffix + ".lock").open("a+b") as stream:
            if stream.seek(0, 2) == 0:
                stream.write(b"0")
                stream.flush()
            deadline = time.monotonic() + 10
            while True:
                try:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("INI-Datei ist bereits durch einen anderen Vorgang gesperrt.")
                    time.sleep(0.05)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

    @classmethod
    def write(cls, path, parser):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                parser.write(stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @classmethod
    def ensure_state(cls, path=None):
        path = Path(path) if path is not None else cls.path()
        with cls.locked(path):
            parser = cls.parser(path)
            changed = False
            for section in parser.sections():
                for obsolete in ("TortoiseGitState", "UpdateState"):
                    if parser.remove_option(section,obsolete):
                        changed = True
            if parser.has_section("APPLICATION") and parser.get("APPLICATION", "update_ini_path", fallback=cls.UPDATE_INI).casefold() == cls.LEGACY_UPDATE_INI.casefold():
                parser.set("APPLICATION", "update_ini_path", cls.UPDATE_INI)
                changed = True
            if not parser.has_section(cls.STATE_SECTION):
                parser.add_section(cls.STATE_SECTION)
                changed = True
            if not parser.has_section(cls.USER_SECTION):
                parser.add_section(cls.USER_SECTION)
                changed = True
            if not parser.has_section(cls.PATH_SECTION):
                parser.add_section(cls.PATH_SECTION)
                changed = True
            if not parser.has_section("APPLICATION"):
                parser.add_section("APPLICATION");changed=True
            if not parser.has_option("APPLICATION","supportMail"):
                parser.set("APPLICATION","supportMail",build_settings.SUPPORT_MAIL or "");changed=True
            if build_settings.SUPPORT_MAIL:
                import hashlib
                mail_revision=hashlib.sha256(build_settings.SUPPORT_MAIL.encode()).hexdigest()
                if parser.get("APPLICATION","support_mail_revision",fallback="")!=mail_revision:
                    parser.set("APPLICATION","supportMail",build_settings.SUPPORT_MAIL)
                    parser.set("APPLICATION","support_mail_revision",mail_revision);changed=True
            # Release defaults fill missing keys below; existing user values always win.
            # Import the previous installer alias once, then remove it everywhere.
            legacy_installer_key="aktuellSilverVersion"
            if not parser.has_option(cls.PATH_SECTION,"silverInstallerPath") and not parser.has_option(cls.STATE_SECTION,"silverInstallerPath"):
                for old_section in (cls.PATH_SECTION,cls.STATE_SECTION):
                    legacy_value=parser.get(old_section,legacy_installer_key,fallback="").strip()
                    if legacy_value:
                        parser.set(cls.PATH_SECTION,"silverInstallerPath",legacy_value)
                        changed=True
                        break
            for old_section in parser.sections():
                if parser.remove_option(old_section,legacy_installer_key):changed=True
            # Preserve explicit USER values; migrate old STATE layouts once.
            for section in (cls.USER_SECTION, cls.STATE_SECTION):
                if parser.has_option(section, "GitLicenceState"):
                    if not parser.has_option(cls.USER_SECTION,"GitUserLicenceState"):
                        parser.set(cls.USER_SECTION,"GitUserLicenceState",parser.get(section,"GitLicenceState"))
                    parser.remove_option(section,"GitLicenceState")
                    changed = True
            for key, value in cls.STATE_DEFAULTS.items():
                section = cls.section_for(key)
                if not parser.has_option(section, key):
                    if key in cls.USER_KEYS or key in cls.PATH_KEYS:
                        value = parser.get(cls.STATE_SECTION,key,fallback=value)
                    parser.set(section, key, value)
                    changed = True
                if (key in cls.USER_KEYS or key in cls.PATH_KEYS) and parser.has_option(cls.STATE_SECTION,key):
                    parser.remove_option(cls.STATE_SECTION,key)
                    changed = True
            if changed:
                cls.write(path, parser)
        return path

    @classmethod
    def state(cls, path=None):
        path = cls.ensure_state(path)
        parser = cls.parser(path)
        result = dict(parser[cls.STATE_SECTION])
        result.update({key:parser.get(cls.section_for(key),key) for key in cls.USER_KEYS|cls.PATH_KEYS})
        for key in cls.BOOLEAN_STATES:
            if result[key].lower() not in ("true", "false"):
                raise ValueError(f"Ungültiger INI-Zustand für {key}: {result[key]}")
            result[key] = result[key].lower() == "true"
        if result["InstalledSilverVersion"].strip().casefold() in ("", "none"):
            result["InstalledSilverVersion"] = None
        return result

    @classmethod
    def set_state(cls, key, value, path=None):
        if key not in cls.STATE_DEFAULTS:
            raise KeyError(key)
        if key in cls.BOOLEAN_STATES:
            if not isinstance(value, bool):
                raise TypeError(f"{key} erfordert bool")
            value = str(value)
        elif value is None and key == "InstalledSilverVersion":
            value = ""
        elif not isinstance(value, str):
            raise TypeError(f"{key} erfordert einen Textwert")
        path = cls.ensure_state(path)
        with cls.locked(path):
            parser = cls.parser(path)
            parser.set(cls.section_for(key), key, value)
            cls.write(path, parser)

    @classmethod
    def sync_update_paths(cls, parser, path=None):
        value=parser.get("PATH","silSetupPath",fallback=parser.get("UPDATE","silSetupPath",fallback="")).strip()
        # Missing/empty/offline manifests must not erase a previously valid path.
        if value and not cls.state(path).get("silSetupPath"):
            cls.set_state("silSetupPath",value,path=path)

    @classmethod
    def sync_support_mail(cls,parser,path=None):
        import re
        values=[value.strip() for section in parser.sections() for key,value in parser.items(section) if key.lower()=="supportmail" and value.strip()]
        if len(values)!=1:return
        value=values[0]
        if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",value):return
        destination=cls.ensure_state(path)
        with cls.locked(destination):
            local=cls.parser(destination)
            if local.get("APPLICATION","supportMail",fallback="")!=value:
                local.set("APPLICATION","supportMail",value);cls.write(destination,local)

    @classmethod
    def export_installation_config(cls, destination, paths=None, support_mail=None):
        """Ship pristine state defaults, never the developer machine's flags."""
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser["APPLICATION"] = {"update_ini_path":cls.UPDATE_INI,"inca_prog_id":"INCA.INCA"}
        parser[cls.STATE_SECTION] = {key:value for key,value in cls.STATE_DEFAULTS.items() if key not in cls.USER_KEYS|cls.PATH_KEYS}
        parser[cls.USER_SECTION] = {key:value for key,value in cls.STATE_DEFAULTS.items() if key in cls.USER_KEYS}
        parser[cls.PATH_SECTION] = {key:value for key,value in cls.STATE_DEFAULTS.items() if key in cls.PATH_KEYS}
        if paths:parser[cls.PATH_SECTION].update(paths)
        parser["APPLICATION"]["supportMail"]=support_mail if support_mail is not None else build_settings.SUPPORT_MAIL
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        cls.write(path, parser)
        return path

    @classmethod
    def load(cls, path=None):
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(path or Runtime.project_root() / "siLAssistent.ini", encoding="utf-8-sig")
        return {"update_ini_path": os.environ.get("SILASSISTENT_UPDATE_INI") or
                parser.get("APPLICATION", "update_ini_path", fallback=cls.UPDATE_INI),
                "silver_home": parser.get("APPLICATION", "silver_home", fallback=""),
                "inca_prog_id": parser.get("APPLICATION", "inca_prog_id", fallback="INCA.INCA")}

    @classmethod
    def version(cls):
        path = Runtime.project_root() / "VERSION"
        return path.read_text(encoding="utf-8-sig").strip()
