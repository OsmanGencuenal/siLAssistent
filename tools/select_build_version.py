"""Interactive version selection before the build; update only latest_version in both manifests."""
import os
import re
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source.core.config import Config

class BuildVersion:
    @classmethod
    def validate(cls,value):
        value=value.strip()
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2,3}",value) or any(int(part)>65535 for part in value.split(".")):
            raise ValueError("Bitte eine Version wie 0.1.0 oder 0.1.0.1 eingeben (Werte 0 bis 65535).")
        return value

    @classmethod
    def atomic_bytes(cls,path,data):
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent,suffix=".tmp",delete=False) as stream:
                temporary=Path(stream.name);stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)

    @classmethod
    def update(cls,value,root=None,remote=None):
        from contextlib import ExitStack
        value=cls.validate(value)
        root=Path(root) if root else Path(__file__).resolve().parents[1]
        local=root/"siLAssistent_Update.ini";remote=Path(remote) if remote else Path(Config.UPDATE_INI)
        version=root/"VERSION"
        paths=[local,remote,version]
        # Read every file before writing: an unavailable share leaves local versions unchanged.
        with ExitStack() as locks:
            for path in paths:
                if not path.is_file():raise FileNotFoundError(str(path))
                locks.enter_context(Config.locked(path))
            previous={path:path.read_bytes() for path in paths}
            changed=[]
            try:
                for path in (local,remote):
                    parser=Config.parser(path)
                    if not parser.has_section("UPDATE"):parser.add_section("UPDATE")
                    for key in list(parser["UPDATE"]):
                        if key.casefold()=="latest_version":parser.remove_option("UPDATE",key)
                    parser.set("UPDATE","latest_version",value)
                    changed.append(path);Config.write(path,parser)
                changed.append(version);cls.atomic_bytes(version,(value+"\n").encode("utf-8"))
            except Exception:
                for path in reversed(changed):cls.atomic_bytes(path,previous[path])
                raise
        return value

    @classmethod
    def prompt(cls,root=None,remote=None,read=input,write=print):
        root=Path(root) if root else Path(__file__).resolve().parents[1]
        current=(root/"VERSION").read_text(encoding="utf-8-sig").strip()
        write("Aktuelle Version :: "+current)
        while True:
            answer=read("Versionsnummer aendern? [J/N] :: ").strip().upper()
            if answer=="N":return cls.validate(current)
            if answer!="J":
                write("Bitte J oder N eingeben.");continue
            while True:
                try:value=cls.validate(read("Versions-Nr :: "))
                except ValueError as error:
                    write(str(error));continue
                break
            cls.update(value,root,remote)
            write("Version "+value+" in VERSION, lokaler und LW-Update-INI gespeichert.")
            return value

if __name__=="__main__":
    try:BuildVersion.prompt()
    except KeyboardInterrupt:
        print("Build abgebrochen.");sys.exit(1)
    except Exception as error:
        print("Version konnte nicht uebernommen werden: "+str(error));sys.exit(1)
