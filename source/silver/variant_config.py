"""Bind vECU variant coding to its SFU parameter without rewriting the XML layout."""
import html
import os
import re
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

class SilverVariantConfig:
    @classmethod
    def prepare(cls,changes,setup_path,entries):
        plan=[]
        for name,payload in changes.items():
            if not isinstance(payload,dict) or not payload.get("variant"):continue
            entry=entries.get(name)
            if entry is None:raise RuntimeError("SFU nicht gefunden: "+name)
            path=Path(entry["path"])
            if not path.is_absolute():path=Path(setup_path).parent/path
            original=path.read_bytes()
            text=original.decode("utf-8-sig")
            root=ET.fromstring(text)
            lines=[node.text or "" for node in root.findall("./modules/module/sil-line")]
            if not any("vecu.dll" in line.lower() and re.search(r"(?<!\S)-d\s+",line) for line in lines):
                raise RuntimeError("VarCode-Verknüpfung der vECU nicht gefunden: "+name)
            argument=re.compile(r'(?<!\S)(-d\s+)(?:"[^"\r\n]*"|[^\s]+)')
            def bind(match):
                line=html.unescape(match.group(2))
                if "vecu.dll" not in line.lower():return match.group(0)
                line=argument.sub(lambda item:item.group(1)+'"${variant_code_string_file}"',line)
                return match.group(1)+html.escape(line,quote=False)+match.group(3)
            updated=re.sub(r"(<sil-line>)(.*?)(</sil-line>)",bind,text,flags=re.S)
            parameter=re.compile(r"(<param>\s*<name>variant_code_string_file</name>\s*<value>)(.*?)(</value>)",re.S)
            if not parameter.search(updated):raise RuntimeError("VarCode-Parameter fehlt in "+name)
            updated=parameter.sub(lambda match:match.group(1)+html.escape(payload["variant"],quote=False)+match.group(3),updated)
            ET.fromstring(updated)
            data=updated.encode("utf-8-sig" if original.startswith(b"\xef\xbb\xbf") else "utf-8")
            if data!=original:plan.append((path,original,data))
        return plan

    @classmethod
    def apply(cls,plan):
        for path,original,data in plan:
            if path.read_bytes()!=original:
                raise RuntimeError("SFU wurde zwischenzeitlich geändert. Bitte Änderungen erneut übernehmen: "+path.name)
            path.with_suffix(path.suffix+".siLAssistent.bak").write_bytes(original)
            handle,temporary=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=path.parent)
            try:
                with os.fdopen(handle,"wb") as stream:stream.write(data)
                os.replace(temporary,path)
            finally:
                if os.path.exists(temporary):os.unlink(temporary)
