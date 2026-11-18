"""SFU parameter-file editing through the central Silver API."""
import shlex
import os
from pathlib import PureWindowsPath,Path
from .methods import Silver

class SilverParameterFiles:
    SESSION="setup-control"
    XML_FLASH_TRIAL=False
    TARGETS=("ECM_MRG12_Slave.sil","ECM_MRG12_Master.sil")

    @classmethod
    def display_path(cls,value,setup_path):
        value=value.strip()
        if not value or not setup_path:return value
        base=Path(setup_path).parent
        # Pure path arithmetic: resolve() can contact slow network shares or
        # inspect junctions and must not run in the GUI's file-selection callback.
        root=Path(os.path.abspath(next((folder for folder in (base,*base.parents) if folder.name.casefold()=="simfiles"),base)))
        candidate=Path(value.replace("\\","/"))
        absolute=Path(os.path.abspath(candidate if candidate.is_absolute() else root/candidate))
        try:return absolute.relative_to(root).as_posix()
        except ValueError:return absolute.as_posix()

    @classmethod
    def parse(cls,value):
        lexer=shlex.shlex(value or "",posix=True);lexer.whitespace_split=True;lexer.escape="";lexer.commenters=""
        tokens=iter(lexer);files=[]
        for token in tokens:
            if token=="-P":files.append(next(tokens))
            elif token.startswith("-P"):files.append(token[2:])
            else:raise ValueError("Parameter_files enthält ein unbekanntes Format: "+token)
        return files

    @classmethod
    def serialize(cls,files):
        result=[]
        for name in files:
            name=name.strip()
            if not name:continue
            if any(c in name for c in ('"',"\n","\r")):raise ValueError("Ungültiger Dateipfad.")
            result.append('-P"'+name+'"' if any(c.isspace() for c in name) else '-P'+name)
        return " ".join(result)

    @classmethod
    def entries(cls):
        result={}
        for uuid in Silver.get_top_level_sfu_uuids(session=cls.SESSION):
            props=Silver.get_sfu_properties(uuid,session=cls.SESSION)
            name=PureWindowsPath(props.get("path","")).name
            if name not in cls.TARGETS:continue
            if name in result:raise RuntimeError("SFU ist mehrfach vorhanden: "+name)
            params=props.get("parameters") or {}
            result[name]={"uuid":uuid,"path":props.get("path",name),"files":cls.parse(params.get("Parameter_files","")),"variant":params.get("variant_code_string_file","")}
        return result

    @classmethod
    def update(cls,name,files,variant=None,entry=None):
        if name not in cls.TARGETS:raise ValueError("Unbekannte SFU.")
        entry=entry if entry is not None else cls.entries().get(name)
        if entry is None:raise RuntimeError("SFU wurde im verbundenen Setup nicht gefunden: "+name)
        # Re-read immediately before writing, preserving unrelated SFU parameters.
        params=dict(Silver.get_sfu_properties(entry["uuid"],session=cls.SESSION).get("parameters") or {})
        params["Parameter_files"]=cls.serialize(files)
        if variant is not None:params["variant_code_string_file"]=variant
        result=Silver.set_sfu_property(entry["uuid"],"parameters",params,session=cls.SESSION)
        if result is False:raise RuntimeError("Silver hat die Änderung nicht übernommen.")

    @classmethod
    def update_many(cls,changes):
        entries=cls.entries()
        for name,payload in changes.items():
            files=payload["files"] if isinstance(payload,dict) else payload
            if isinstance(payload,dict) and payload.get("variant") and PureWindowsPath(payload["variant"]).suffix.lower()!=".aed":raise ValueError("Bitte eine AED-Datei verwenden.")
            if name not in entries or name not in cls.TARGETS:raise RuntimeError("SFU nicht gefunden: "+name)
            cls.serialize(files)
            if any(PureWindowsPath(value).suffix.lower()!=".dcm" for value in files if value.strip()):raise ValueError("Bitte nur DCM-Dateien verwenden.")
        for name,payload in changes.items():
            if isinstance(payload,dict):cls.update(name,payload["files"],payload.get("variant"),entry=entries[name])
            else:cls.update(name,payload,entry=entries[name])

    @classmethod
    def apply_and_reload(cls,changes,setup_path,progress=None):
        if cls.XML_FLASH_TRIAL:return cls.apply_xml_and_reload(changes,setup_path,progress)
        return cls.apply_via_api(changes,setup_path,progress)

    @classmethod
    def apply_xml_and_reload(cls,changes,setup_path,progress=None):
        from .xml_flash import SilverXmlFlash as Xml
        # Validate all XML and requested fields before stopping the simulation.
        Xml.prepare(changes,setup_path)
        if progress:progress("Silver-Cleanup wird abgewartet …")
        Silver.stop(session=cls.SESSION)
        if progress:progress("Aktueller Projektstand wird vor der XML-Änderung gesichert …")
        if Silver.save(setup_path,session=cls.SESSION) is False:raise RuntimeError("Projekt konnte vor dem XML-Flashen nicht gespeichert werden.")
        plan=Xml.prepare(changes,setup_path)
        if progress:progress("DCM-/AED-Einträge werden direkt im XML gespeichert …")
        Xml.commit(plan)
        try:
            if progress:progress("Geänderte SIL-Datei wird neu eingelesen und geladen …")
            Silver.open(setup_path,session=cls.SESSION)
            if not cls.verify_flash(changes):raise RuntimeError("Silver meldet andere DCM-/AED-Werte als im XML vorgegeben.")
        except Exception as error:
            Xml.restore(plan)
            raise RuntimeError("XML-Flashen nicht erfolgreich. Die geänderten XML-Dateien wurden auf den Stand vor dem Versuch zurückgesetzt. Bitte das Setup neu laden. Ursache: "+str(error)) from error

    @classmethod
    def verify_flash(cls,changes):
        entries=cls.entries()
        normalize=lambda value:str(PureWindowsPath(value)).casefold()
        for name,payload in changes.items():
            files=payload["files"] if isinstance(payload,dict) else payload
            if name not in entries:return False
            if [normalize(value) for value in entries[name]["files"]]!=[normalize(value) for value in files if value.strip()]:return False
        return cls.verify_variants(changes)

    @classmethod
    def apply_via_api(cls,changes,setup_path,progress=None):
        # Commit SFU changes in the currently open configuration.
        # Keep editor-save handling active; do not reopen/clear the whole project.
        if progress:progress("Datenstand und Varianten-Kodierung werden in Silver übernommen …")
        from .variant_config import SilverVariantConfig
        variant_changes={name:payload for name,payload in changes.items() if isinstance(payload,dict) and payload.get("variant")}
        variant_plan=SilverVariantConfig.prepare(variant_changes,setup_path,cls.entries()) if variant_changes else []
        if progress:progress("Silver beendet die Simulation und führt den Cleanup aus. Bitte warten …")
        Silver.stop(session=cls.SESSION)
        cls.update_many(changes)
        if progress:progress("Änderungen werden gespeichert …")
        result=Silver.save(setup_path,session=cls.SESSION)
        if result is False:raise RuntimeError("Setup konnte nicht gespeichert werden.")
        SilverVariantConfig.apply(variant_plan)
        if progress:progress("Setup wird neu geladen. Bitte warten …")
        Silver.reload(session=cls.SESSION)
        # A module-editor Save confirmed during reload can dirty the project again.
        if progress:progress("Setup wird abschließend gespeichert …")
        if Silver.save(setup_path,session=cls.SESSION) is False:
            raise RuntimeError("Setup konnte nach dem Übernehmen nicht gespeichert werden.")
        if not cls.verify_variants(changes):
            if progress:progress("Silver-Editor enthält noch alte Werte. Konfiguration wird erneut eingelesen …")
            # Reload alone does not discard Silver's stale SFU editor buffer.
            # Reopen only on a verified mismatch, while the scoped Save handler is active.
            Silver.open(setup_path,session=cls.SESSION)
            Silver.stop(session=cls.SESSION)
            cls.update_many(changes)
            if Silver.save(setup_path,session=cls.SESSION) is False:
                raise RuntimeError("Variantenkodierung konnte nicht gespeichert werden.")
            if progress:progress("Variantenkodierung wird geladen und geprüft …")
            Silver.reload(session=cls.SESSION)
            if not cls.verify_variants(changes):
                raise RuntimeError("Silver hat die gewählte Variantenkodierung nicht übernommen. Die Änderung wurde nicht als erfolgreich bestätigt.")


    @classmethod
    def verify_variants(cls,changes):
        """Check effective SFU values and expanded vECU arguments after loading."""
        import re
        variants={name:payload["variant"] for name,payload in changes.items()
                  if isinstance(payload,dict) and payload.get("variant")}
        if not variants:return True
        entries=cls.entries()
        normalize=lambda value:str(PureWindowsPath(value)).casefold()
        modules=None
        for name,expected in variants.items():
            entry=entries.get(name)
            if entry is None or normalize(entry["variant"])!=normalize(expected):return False
            if modules is None:modules=Silver.get_module_uuids(session=cls.SESSION)
            found=False
            for uuid in modules:
                if not uuid.startswith(entry["uuid"]+"::"):continue
                props=Silver.get_module_properties(uuid,session=cls.SESSION)
                line=props.get("preview_sil_line") or ""
                if "vecu.dll" not in line.lower():continue
                match=re.search(r'(?<!\S)-d\s+(?:"([^"\r\n]*)"|(\S+))',line)
                if not match or normalize(match.group(1) or match.group(2))!=normalize(expected):return False
                found=True
            if not found:return False
        return True
