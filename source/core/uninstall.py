"""Export user settings before invoking the installed native uninstaller."""
import re
import subprocess
from pathlib import Path
from .runtime import Runtime
from .user_config import UserConfig

class Uninstall:
    @classmethod
    def export_user_config(cls,destination):
        root=Runtime.project_root().resolve()
        target=Path(destination)
        if target.resolve().is_relative_to(root):
            raise ValueError("Bitte die Sicherung außerhalb des Installationsordners speichern.")
        return UserConfig.export(target,root/"siLAssistent.ini")

    @classmethod
    def start(cls,filename):
        root=Runtime.project_root().resolve();target=Path(filename).resolve()
        if target.parent!=root or not re.fullmatch(r"unins[0-9]{3,}\.exe",target.name,re.I) or not target.is_file():
            raise ValueError("Der Deinstaller dieser siLAssistent-Installation wurde nicht gefunden.")
        return subprocess.Popen([str(target)],cwd=str(root),creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
