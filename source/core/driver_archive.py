"""Unpack only the compatible offline Edge driver into the user cache."""
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from .runtime import Runtime

class DriverArchive:
    @classmethod
    def unpack(cls,archive):
        archive=Path(archive)
        version=archive.parent.name
        import re
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}",version):raise ValueError("Ungültige Edge-Treiberversion")
        manifest=json.loads((archive.parent.parent/"manifest.json").read_text(encoding="utf-8"))
        if version not in manifest["versions"]:raise ValueError("Edge-Treiber fehlt im Manifest")
        digest=manifest.get("sha256",{}).get(version)
        if not digest:raise ValueError("Edge-Treiber-Prüfsumme fehlt")
        target=Runtime.data_root()/"drivers"/version/"msedgedriver.exe"
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==digest:return target
        with zipfile.ZipFile(archive) as package:content=package.read("msedgedriver.exe")
        if not content.startswith(b"MZ") or hashlib.sha256(content).hexdigest()!=digest:raise ValueError("Edge-Treiberarchiv ist beschädigt")
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent,suffix=".tmp",delete=False) as stream:
                temporary=Path(stream.name);stream.write(content)
            os.replace(temporary,target)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
        return target
