"""Discover selectable Silver setups directly inside the configured SimFiles folder."""
from pathlib import Path
from ..core.config import Config

class SetupControl:
    SOURCES={"Git":"GitLocalRepoPath","Lokale manuelle Kopie":"DriveSetupLocalPath"}

    @classmethod
    def list_setups(cls,source):
        if source not in cls.SOURCES:raise ValueError("Unbekannte Setup-Auswahl.")
        value=Config.state()[cls.SOURCES[source]].strip()
        if not value:
            return {"path":"","files":[],"message":"Für "+source+" ist noch kein lokaler SimFiles-Pfad eingerichtet."}
        root=Path(value).expanduser().resolve()
        if root.name.casefold()!="simfiles" or not root.is_dir():
            raise ValueError("Der gespeicherte SimFiles-Ordner ist nicht vorhanden. Bitte den lokalen Setup-Pfad prüfen.")
        files=sorted((item for item in root.iterdir() if item.is_file() and item.suffix.casefold()==".sil"),key=lambda item:item.name.casefold())
        return {"path":str(root),"files":[str(item) for item in files],"message":"" if files else "Keine .sil-Dateien direkt im SimFiles-Ordner gefunden."}

    @classmethod
    def open(cls,parent=None):
        from .setup_control_window import SetupControlWindow
        return SetupControlWindow.open(parent)
