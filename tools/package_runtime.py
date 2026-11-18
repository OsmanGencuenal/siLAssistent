"""Lossless offline driver packaging and removal of non-Windows build artifacts."""
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

class RuntimePackage:
    @classmethod
    def package_drivers(cls,source,destination):
        source=Path(source).resolve();destination=Path(destination).resolve()
        if destination==source or destination.is_relative_to(source):raise ValueError("Build destination must differ from driver source")
        manifest=json.loads((source/"manifest.json").read_text(encoding="utf-8"))
        destination.mkdir(parents=True,exist_ok=True)
        hashes={};original=0;packed=0
        for version in manifest["versions"]:
            if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}",version):raise ValueError("Invalid driver version")
            driver=source/version/"msedgedriver.exe"
            folder=destination/version;folder.mkdir(parents=True,exist_ok=True)
            archive=folder/"edgedriver.zip";temporary=archive.with_suffix(".partial")
            try:
                with zipfile.ZipFile(temporary,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as package:
                    package.write(driver,"msedgedriver.exe")
                with zipfile.ZipFile(temporary) as package:
                    if package.getinfo("msedgedriver.exe").file_size!=driver.stat().st_size:raise ValueError("Incomplete driver archive")
                os.replace(temporary,archive)
            finally:temporary.unlink(missing_ok=True)
            hashes[version]=hashlib.sha256(driver.read_bytes()).hexdigest()
            original+=driver.stat().st_size;packed+=archive.stat().st_size
            licence=source/version/"LICENSE"
            if licence.is_file():shutil.copy2(licence,folder/"LICENSE")
            # Only obsolete generated copies are removed; source files stay intact.
            (folder/"msedgedriver.exe").unlink(missing_ok=True)
        manifest.update(storage="zip",sha256=hashes)
        (destination/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        return {"original_bytes":original,"packed_bytes":packed,"saved_bytes":original-packed}

    @classmethod
    def prepare(cls,source,distribution):
        root=Path(distribution).resolve()
        if not root.name.endswith(".dist") or not (root/"siLAssistent.exe").is_file():raise ValueError("Not a generated siLAssistent distribution")
        result=cls.package_drivers(source,root/"drivers")
        for platform in ("linux-arm64","linux-x86_64","macos"):
            target=(root/"selenium/webdriver/common"/platform).resolve()
            if not target.is_relative_to(root):raise ValueError("Cleanup target outside distribution")
            if target.is_dir():shutil.rmtree(target)
        return result

if __name__=="__main__":print(json.dumps(RuntimePackage.prepare(sys.argv[1],sys.argv[2])))
