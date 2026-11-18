"""Minimal, reversible XML edits for the explicit Flash/Übernehmen action."""
import html
import os
import re
import tempfile
from pathlib import Path,PureWindowsPath
from xml.etree import ElementTree as ET

class SilverXmlFlash:
    @classmethod
    def read(cls,path):
        data=path.read_bytes()
        encoding="utf-8-sig" if data.startswith(b"\xef\xbb\xbf") else "utf-8"
        if data.startswith((b"\xff\xfe",b"\xfe\xff")):encoding="utf-16"
        text=data.decode(encoding);ET.fromstring(text)
        return data,text,encoding

    @classmethod
    def parameter(cls,block,name,value):
        pattern=re.compile(r"(<param\b[^>]*>\s*<name>"+re.escape(name)+r"</name>\s*<value>)(.*?)(</value>)",re.S)
        matches=list(pattern.finditer(block))
        if len(matches)>1:raise ValueError("Mehrdeutiger XML-Parameter: "+name)
        escaped=html.escape(value,quote=False)
        if matches:
            match=matches[0]
            if html.unescape(match.group(2))==value:return block
            return block[:match.start(2)]+escaped+block[match.end(2):]
        empty=re.search(r"<param\b[^>]*>\s*<name>"+re.escape(name)+r"</name>\s*<value\s*/>",block)
        if empty:
            return block[:empty.start()]+block[empty.start():empty.end()].replace("<value/>","<value>"+escaped+"</value>").replace("<value />","<value>"+escaped+"</value>")+block[empty.end():]
        newline="\r\n" if "\r\n" in block else "\n"
        addition="<param><name>"+name+"</name><value>"+escaped+"</value></param>"
        if "</parameters>" in block:return block.replace("</parameters>","  "+addition+newline+"      </parameters>",1)
        return re.sub(r"<parameters\s*/>",lambda match:"<parameters>"+addition+"</parameters>",block,count=1)

    @classmethod
    def prepare(cls,changes,setup_path):
        from .parameter_files import SilverParameterFiles as Files
        setup=Path(setup_path);original,text,encoding=cls.read(setup)
        root=ET.fromstring(text);sfus={}
        for node in root.findall("./modules/sfu"):
            name=PureWindowsPath(node.findtext("path") or "").name
            if name in changes:
                if name in sfus:raise ValueError("SFU mehrfach vorhanden: "+name)
                sfus[name]=node
        normalized={}
        for name,payload in changes.items():
            if name not in Files.TARGETS or name not in sfus:raise ValueError("SFU nicht gefunden: "+name)
            files=payload["files"] if isinstance(payload,dict) else payload
            if not files or not files[0].strip():raise ValueError("Haupt-DCM fehlt: "+name)
            if any(PureWindowsPath(value).suffix.lower()!=".dcm" for value in files if value.strip()):raise ValueError("Bitte nur DCM-Dateien verwenden.")
            values={"Parameter_files":Files.serialize(files)}
            if isinstance(payload,dict) and "variant" in payload:
                variant=payload["variant"].strip()
                if variant and PureWindowsPath(variant).suffix.lower()!=".aed":raise ValueError("Bitte eine AED-Datei verwenden.")
                values["variant_code_string_file"]=variant
            normalized[name]=values
        modules=re.search(r"(<modules\b[^>]*>)(.*?)(</modules>)",text,re.S)
        if not modules:raise ValueError("SIL-Modulbereich fehlt.")
        found=set()
        def replace_sfu(match):
            block=match.group(0);node=ET.fromstring(block)
            name=PureWindowsPath(node.findtext("path") or "").name
            if name not in normalized:return block
            found.add(name)
            for key,value in normalized[name].items():block=cls.parameter(block,key,value)
            actual={item.findtext("name"):item.findtext("value") or "" for item in ET.fromstring(block).findall("./parameters/param")}
            if any(actual.get(key)!=value for key,value in normalized[name].items()):raise ValueError("XML-Parameter konnte nicht gesetzt werden: "+name)
            return block
        body=re.sub(r"<sfu\b[^>]*>.*?</sfu>",replace_sfu,modules.group(2),flags=re.S)
        if found!=set(normalized):raise ValueError("SFU-XML konnte nicht eindeutig zugeordnet werden.")
        updated=text[:modules.start(2)]+body+text[modules.end(2):]
        ET.fromstring(updated)
        plan=[]
        if updated!=text:plan.append((setup,original,updated.encode(encoding)))
        # Only touch an SFU file if its vECU still ignores the SFU parameter.
        for name,values in normalized.items():
            if not values.get("variant_code_string_file"):continue
            path=Path((sfus[name].findtext("path") or "").replace("\\","/"))
            if not path.is_absolute():path=setup.parent/path
            old,source,codec=cls.read(path)
            matched=[0]
            argument=re.compile(r'(?<!\S)(-d\s+)(?:"([^"\r\n]*)"|(\S+))')
            def bind(match):
                raw=match.group(2);line=html.unescape(raw)
                if "vecu.dll" not in line.lower():return match.group(0)
                option=argument.search(line)
                if not option:return match.group(0)
                matched[0]+=1
                if (option.group(2) or option.group(3)) in ("${variant_code_string_file}","$variant_code_string_file"):return match.group(0)
                line=line[:option.start()]+option.group(1)+'"${variant_code_string_file}"'+line[option.end():]
                return match.group(1)+html.escape(line,quote=False)+match.group(3)
            amended=re.sub(r"(<sil-line>)(.*?)(</sil-line>)",bind,source,flags=re.S)
            if matched[0]!=1:raise ValueError("vECU-AED-Verknüpfung nicht eindeutig: "+name)
            ET.fromstring(amended)
            if amended!=source:plan.append((path,old,amended.encode(codec)))
        return plan

    @classmethod
    def write_atomic(cls,path,data):
        handle,temporary=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=path.parent)
        try:
            with os.fdopen(handle,"wb") as stream:stream.write(data)
            os.replace(temporary,path)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)

    @classmethod
    def commit(cls,plan):
        for path,original,_ in plan:
            if path.read_bytes()!=original:raise RuntimeError("SIL-Datei wurde zwischenzeitlich geändert: "+path.name)
        written=[]
        try:
            for path,original,data in plan:
                path.with_suffix(path.suffix+".siLAssistent_xml_flash.bak").write_bytes(original)
                cls.write_atomic(path,data);written.append((path,original,data))
        except Exception:
            cls.restore(written);raise

    @classmethod
    def restore(cls,plan):
        for path,original,data in reversed(plan):
            if path.read_bytes()!=data:raise RuntimeError("XML-Rücknahme nicht möglich: Datei wurde erneut geändert: "+path.name)
            cls.write_atomic(path,original)
