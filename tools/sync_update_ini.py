"""Copy the developer update INI to the explicitly configured release share."""
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source.core.config import Config
from source.core.release_paths import ReleasePaths

class UpdateIniSync:
    @classmethod
    def copy(cls,source=None,destination=None):
        source=Path(source) if source else Path(__file__).resolve().parents[1]/"siLAssistent_Update.ini"
        destination=Path(destination) if destination else Path(Config.UPDATE_INI)
        if source.resolve()==destination.resolve():return False
        ReleasePaths.read(source)
        payload=source.read_bytes()
        if destination.is_file() and destination.read_bytes()==payload:return False
        if not destination.parent.is_dir():raise FileNotFoundError("LW-INI-Verzeichnis ist nicht erreichbar: "+str(destination.parent))
        previous=Config.parser(destination);proposed=Config.parser(source)
        # A template must not disable an already published installer by accident.
        for key in ("installer_path","sha256"):
            if previous.get("UPDATE",key,fallback="").strip() and not proposed.get("UPDATE",key,fallback="").strip():
                raise ValueError("Lokale Vorlage würde veröffentlichte Releaseinformationen leeren: "+key)
        if destination.is_file():shutil.copy2(destination,destination.with_suffix(destination.suffix+".siLAssistent.bak"))
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent,prefix=destination.name+".",suffix=".tmp",delete=False) as stream:
                temporary=Path(stream.name);stream.write(payload);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,destination)
            if hashlib.sha256(destination.read_bytes()).digest()!=hashlib.sha256(payload).digest():raise OSError("LW-INI-Prüfsumme stimmt nicht überein.")
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
        return True

if __name__=="__main__":
    print("LW-Update-INI synchronisiert." if UpdateIniSync.copy() else "LW-Update-INI ist bereits aktuell.")
