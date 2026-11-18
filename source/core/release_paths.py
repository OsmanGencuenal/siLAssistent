"""Paths managed centrally in the release manifest and frozen in each build."""
from pathlib import Path
from urllib.parse import urlsplit
from .config import Config

class ReleasePaths:
    KEYS=("silverInstallerPath","silSetupPath","GitInstallationPath","GitSetupRepo")

    @classmethod
    def read(cls,ini):
        parser=Config.parser(Path(ini))
        values={key:parser.get("PATH",key,fallback="").strip() for key in cls.KEYS}
        for key in ("silverInstallerPath","silSetupPath","GitInstallationPath"):
            values[key]=cls.normalize_path(values[key])
        for key,value in values.items():
            if not value or any(character in value for character in ('\n','\r','"','{','}')):
                raise ValueError("[PATH]/"+key+" fehlt oder ist ungültig in der LW-Update-INI.")
        for key in ("silverInstallerPath","GitInstallationPath"):
            if not Path(values[key]).is_absolute() or Path(values[key]).suffix.casefold()!=".exe":
                raise ValueError(key+" muss einen vollständigen EXE-Pfad enthalten.")
        if not Path(values["silSetupPath"]).is_absolute():raise ValueError("silSetupPath muss ein vollständiger Ordnerpfad sein.")
        cls.validate_repository(values["GitSetupRepo"])
        return values

    @classmethod
    def normalize_path(cls,value):
        # INI paths are literal: tolerate mistakenly doubled JSON-style backslashes.
        if value.startswith("\\\\"):
            return "\\\\"+"\\".join(part for part in value.split("\\") if part)
        return value

    @classmethod
    def validate_repository(cls,value):
        url=urlsplit(value)
        if url.scheme!="https" or not url.hostname or url.username or url.password or url.query or url.fragment or len(url.path.strip('/').split('/'))!=2:
            raise ValueError("GitSetupRepo muss eine HTTPS-Repo-URL ohne Zugangsdaten enthalten.")
        return value
