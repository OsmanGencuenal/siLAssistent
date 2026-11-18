"""Build-bound Silver license servers, never imported from prior installations."""
import configparser
import re
import sys
from pathlib import Path
from ..core import build_settings
from ..core.runtime import Runtime

class SilverLicences:
    @classmethod
    def normalize(cls, value):
        values=re.split(r"[,;\s]+",value.strip()) if isinstance(value,str) else list(value)
        result=[]
        for value in values:
            match=re.fullmatch(r"([0-9]{1,5})@([A-Za-z0-9][A-Za-z0-9.-]*)",value)
            if not match or not 1<=int(match.group(1))<=65535:
                raise ValueError("silverLicences muss gültige Lizenzserver im Format Port@Server enthalten.")
            if value not in result:
                result.append(value)
        if not result:
            raise ValueError("silverLicences darf nicht leer sein.")
        return tuple(result)

    @classmethod
    def read(cls, ini):
        parser=configparser.ConfigParser(interpolation=None)
        parser.read(Path(ini),encoding="utf-8-sig")
        value=parser.get("UPDATE","silverLicences",fallback="")
        return cls.normalize(value)

    @classmethod
    def servers(cls):
        embedded=build_settings.SILVER_LICENCE_SERVERS
        if embedded:
            return cls.normalize(embedded)
        if "__compiled__" in globals() or getattr(sys,"frozen",False):
            raise ValueError("Lizenzserver fehlen in diesem Build. Bitte einen vollständigen siLAssistent-Build verwenden.")
        return cls.read(Runtime.project_root()/"siLAssistent_Update.ini")

    @classmethod
    def wizard_value(cls):
        return ",".join(cls.servers())

    @classmethod
    def environment_value(cls):
        return ";".join(cls.servers())
