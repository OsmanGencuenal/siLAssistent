"""Export/import of USER values; machine paths and installation state stay local."""
import configparser
from pathlib import Path
from .config import Config


class UserConfig:
    @classmethod
    def export(cls,destination,local_ini=None):
        source=Config.ensure_state(local_ini)
        target=Path(destination)
        if target.resolve()==source.resolve():
            raise ValueError("Die lokale Konfiguration darf nicht als Exportziel überschrieben werden.")
        parser=configparser.ConfigParser(interpolation=None)
        parser.optionxform=str
        # Snapshot under the same lock used by all configuration writers.
        with Config.locked(source):
            local=Config.parser(source)
            parser["USER"]=dict(local.items("USER",raw=True))
        target.parent.mkdir(parents=True,exist_ok=True)
        Config.write(target,parser)
        return target

    @classmethod
    def read_export(cls,source):
        parser=Config.parser(Path(source))
        if parser.defaults() or parser.sections()!=["USER"]:
            raise ValueError("Bitte eine exportierte Benutzer-Konfiguration mit ausschließlich dem Abschnitt [USER] auswählen.")
        values={}
        known={key.casefold():key for key in Config.USER_KEYS}
        for key,value in parser.items("USER",raw=True):
            canonical=known.get(key.casefold(),key)
            if canonical in values:
                raise ValueError("Doppelter Benutzer-Schlüssel: "+canonical)
            if canonical in Config.BOOLEAN_STATES:
                if value.strip().casefold() not in ("true","false"):
                    raise ValueError(canonical+" muss True oder False enthalten.")
                value=str(value.strip().casefold()=="true")
            values[canonical]=value
        if not values:raise ValueError("Die Exportdatei enthält keine Benutzer-Einstellungen.")
        return values

    @classmethod
    def import_file(cls,source,local_ini=None):
        values=cls.read_export(source)  # Validate the complete file before writing anything.
        destination=Config.ensure_state(local_ini)
        with Config.locked(destination):
            parser=Config.parser(destination)
            for key,value in values.items():parser.set("USER",key,value)
            Config.write(destination,parser)
        return len(values)
