"""Validate release contents without shipping this development tool."""
import json
import sys
from pathlib import Path

class DistributionCheck:
    REQUIRED=("siLAssistent.exe","siLAssistent.ini","VERSION","icons/Main.ico","icons/Support.ico",
              "source/inca/catalog.json","source/silver/catalog.json",
              "drivers/manifest.json","selenium/webdriver/common/windows/selenium-manager.exe")
    DEVELOPMENT=frozenset(("tests","docs","backups","proposals","__pycache__",".pytest_cache",".git",".build-env","_pytest"))

    @classmethod
    def inspect(cls,directory):
        root=Path(directory)
        missing=[name for name in cls.REQUIRED if not (root/name).is_file()]
        files=list(root.rglob("*"))
        unwanted=[str(path.relative_to(root)) for path in files if any(part.casefold() in cls.DEVELOPMENT for part in path.relative_to(root).parts)]
        unwanted += [str(path.relative_to(root)) for path in files if path.is_file() and (path.suffix.casefold() in (".bat",".ps1",".lock") or path.name.casefold().startswith("pytest"))]
        if missing or unwanted:raise ValueError(f"Missing runtime files: {missing}; development artifacts: {unwanted[:20]}")
        manifest=json.loads((root/"drivers/manifest.json").read_text(encoding="utf-8"))
        import zipfile
        for version in manifest["versions"]:
            archive=root/"drivers"/version/"edgedriver.zip"
            if manifest.get("storage")=="zip":
                if not archive.is_file():raise ValueError("Offline Edge driver archive missing: "+version)
                with zipfile.ZipFile(archive) as package:package.getinfo("msedgedriver.exe")
            elif not (root/"drivers"/version/"msedgedriver.exe").is_file():raise ValueError("Edge driver missing: "+version)
        return {"files":sum(path.is_file() for path in files),"bytes":sum(path.stat().st_size for path in files if path.is_file()),"runtime_only":True}

if __name__=="__main__":
    print(json.dumps(DistributionCheck.inspect(sys.argv[1])))
