"""Row-based grouped ECM flash-file editor."""
from pathlib import Path
from PySide6.QtCore import QSize,Qt,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,QFileDialog,QScrollArea,QCheckBox,QLayout
from ..silver.parameter_files import SilverParameterFiles
from ..ui.dialogs import Dialogs
from ..ui.button_gradients import ButtonGradients

class ParameterFilesPanel:
    @classmethod
    def create(cls,window,dispatch):
        panel=QScrollArea();panel.setWidgetResizable(True)
        panel._entries={};panel._dirty=set();panel._sections={};panel._dispatch=dispatch;panel._owner=window
        content=QWidget();layout=QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        header=QHBoxLayout();title=QLabel("Flashen ::");title.setStyleSheet("color:#facc15; font:700 16pt 'Segoe UI';")
        grouped=QCheckBox("Gruppieren");grouped.setChecked(False);panel._grouped=grouped
        ButtonGradients.apply(grouped,"#fed7aa",padding="8px 12px",checked="#99f6e4")
        from ..ui.checkboxes import Checkboxes
        Checkboxes.full_click(grouped)
        flash=QPushButton("Flashen");flash.setObjectName("flashParameters");panel._flash=flash
        flash.setProperty("suiteButtonFrame",True)
        flash.setStyleSheet("QPushButton {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #f8df87,stop:1 #d9b344); color:#172554; border:2px solid #fff0b5; border-radius:6px; padding:8px 20px; font-weight:700;} QPushButton:hover {background:#f9e8ad;} QPushButton:pressed {background:#d4ab39;} QPushButton:disabled {background:#343440; color:#9399a8; border-color:#55596a;}")
        flash.setEnabled(False);flash.clicked.connect(lambda:cls.apply(panel))
        header.addWidget(title);header.addStretch();header.addWidget(flash);header.addWidget(grouped);layout.addLayout(header)
        for name in SilverParameterFiles.TARGETS:
            heading=QLabel("Slave ::" if "Slave" in name else "Master ::");heading.setStyleSheet("color:#86efac; font:700 16pt 'Segoe UI';")
            section_header=QHBoxLayout();section_header.addWidget(heading,1)
            layout.addLayout(section_header)
            variant_label=QLabel("Varianten-Kodierung ::");variant_label.setStyleSheet("color:#c4b5fd; font:700 14pt 'Segoe UI';");layout.addWidget(variant_label)
            variant_row=QHBoxLayout();variant=QLineEdit();variant.setPlaceholderText("—");variant.setEnabled(False)
            variant.setStyleSheet("QLineEdit {background:#fce7f3; color:#172554; border:1px solid #64748b; padding:5px;} QLineEdit:disabled {background:#2a2a3e; color:#94a3b8;}")
            from .dcm_editor import DcmEditor
            from ..stand_management.git_window import GitWindow
            variant_editor=QPushButton();variant_editor.setIcon(DcmEditor.icon());variant_editor.setFixedWidth(32);ButtonGradients.apply(variant_editor,"#fca5a5")
            variant_browse=QPushButton();variant_browse.setIcon(GitWindow.folder_icon());variant_browse.setIconSize(QSize(18,18));variant_browse.setFixedWidth(32);ButtonGradients.apply(variant_browse,"#facc15")
            variant_editor.setToolTip("AED im Editor öffnen");variant_browse.setToolTip("AED-Datei auswählen")
            variant.editingFinished.connect(lambda name=name,edit=variant:cls.change_variant(panel,name,edit.text()))
            variant_editor.clicked.connect(lambda checked=False,edit=variant:cls.open_editor(panel,edit))
            variant_browse.clicked.connect(lambda checked=False,name=name:cls.browse_variant(panel,name))
            for widget in (variant,variant_editor,variant_browse):variant_row.addWidget(widget,1 if widget is variant else 0)
            layout.addLayout(variant_row)
            data_label=QLabel("Datenstand ::");data_label.setStyleSheet("color:#40e0d0; font:700 14pt 'Segoe UI';");layout.addWidget(data_label)
            data_scroll=QScrollArea();data_scroll.setWidgetResizable(True)
            data_scroll.setObjectName("dcmScrollSlave" if "Slave" in name else "dcmScrollMaster")
            data_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            data_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            data_content=QWidget();rows=QVBoxLayout(data_content)
            rows.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
            rows.setContentsMargins(0,0,0,0);rows.setSpacing(6);rows.setAlignment(Qt.AlignmentFlag.AlignTop)
            data_scroll.setWidget(data_content);layout.addWidget(data_scroll,1)
            panel._sections[name]={"scroll":data_scroll,"layout":rows,"edits":[],"apply":flash,"buttons":[],"variant":variant,"variant_editor":variant_editor,"variant_browse":variant_browse}
        panel.setWidget(content)
        cls.populate(panel,{})
        grouped.toggled.connect(lambda checked:cls.grouping_changed(panel,checked))
        QTimer.singleShot(0,lambda:cls.fit_lists(panel))
        return panel

    @classmethod
    def populate(cls,panel,entries):
        selected=getattr(panel._owner,"_setup_control",{}).get("selected")
        entries={name:{**entry,"files":[SilverParameterFiles.display_path(value,selected) for value in entry["files"]]} for name,entry in entries.items()}
        panel._entries=entries;panel._dirty.clear()
        import copy
        panel._baseline=copy.deepcopy(entries)
        panel._flash.setEnabled(bool(entries))
        for name,section in panel._sections.items():
            rows=section["layout"]
            while rows.count():
                item=rows.takeAt(0);item.widget().deleteLater()
            section["edits"]=[];section["buttons"]=[]
            entry=entries.get(name)
            cls.variant_display(section,entry,selected)
            for index,value in enumerate((entry["files"] if entry else [])+[""]):
                cls.add_row(panel,name,index,value,entry is not None)
        cls.fit_lists(panel)

    @classmethod
    def fit_lists(cls,panel):
        # Equal minimums and equal layout stretch keep both lists balanced.
        # Use loaded data, not effective button state (disabled while loading).
        height=max((section["layout"].itemAt(i).widget().sizeHint().height()
                    for section in panel._sections.values()
                    for i in range(section["layout"].count())),default=36)
        height=max(32,height)
        visible_rows=4 if panel._entries else 1
        for section in panel._sections.values():
            rows=section["layout"]
            section["scroll"].setMinimumHeight(visible_rows*height+(visible_rows-1)*rows.spacing()+4)

    @classmethod
    def variant_display(cls,section,entry,selected=None):
        value=SilverParameterFiles.display_path((entry or {}).get("variant",""),selected)
        section["variant"].setText(value);section["variant"].setToolTip(value)
        section["variant"].setPlaceholderText("AED-Datei laden ..." if entry is not None else "—")
        for key in ("variant","variant_browse"):section[key].setEnabled(entry is not None)
        section["variant_editor"].setEnabled(entry is not None and bool(value))

    @classmethod
    def browse_variant(cls,panel,name):
        folder=cls.default_directory(panel,name).parent/"VarCode"
        filename,_=QFileDialog.getOpenFileName(panel._owner,"AED-Datei auswählen",str(folder),"AED-Dateien (*.aed *.AED)")
        if filename:cls.selection_progress(panel,filename,lambda:cls.change_variant(panel,name,filename))

    @classmethod
    def change_variant(cls,panel,name,value):
        selected=getattr(panel._owner,"_setup_control",{}).get("selected")
        value=SilverParameterFiles.display_path(value,selected)
        if value==panel._entries.get(name,{}).get("variant",""):return
        if value and Path(value).suffix.lower()!=".aed":
            Dialogs.message("AED-Datei erforderlich","Bitte eine AED-Datei auswählen.",panel._owner);return
        names=list(SilverParameterFiles.TARGETS) if panel._grouped.isChecked() else [name]
        if any(target not in panel._entries for target in names):
            Dialogs.message("SFU nicht vorhanden","Gruppieren benötigt Master und Slave.",panel._owner);return
        for target in names:
            panel._entries[target]["variant"]=value
            cls.variant_display(panel._sections[target],panel._entries[target],selected)
        panel._dirty.update(names)

    @classmethod
    def add_row(cls,panel,name,index,value,enabled):
        from ..stand_management.git_window import GitWindow
        row=QWidget();layout=QHBoxLayout(row);layout.setContentsMargins(0,0,0,0)
        edit=QLineEdit(value);edit.setToolTip(value);edit.setPlaceholderText("Haupt-DCM-Datei laden" if index==0 else "Weitere DCM-Datei laden ....")
        cls.style_file(edit,index,value)
        if not enabled:
            edit.setPlaceholderText("—")
            edit.setStyleSheet("QLineEdit {placeholder-text-color:#94a3b8; color:#94a3b8; background:#2a2a3e;}")
            edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        browse=QPushButton();browse.setIcon(GitWindow.folder_icon());browse.setIconSize(QSize(18,18));browse.setFixedWidth(32)
        browse.setToolTip("DCM-Datei für diese Zeile auswählen")
        ButtonGradients.apply(browse,"#facc15")
        edit.setEnabled(enabled);browse.setEnabled(enabled)
        edit.editingFinished.connect(lambda:cls.change(panel,name,index,edit.text()))
        browse.clicked.connect(lambda:cls.browse(panel,name,index,edit))
        remove=QPushButton("×");remove.setToolTip("DCM entfernen – wirksam nach Flashen")
        remove.setFixedWidth(30);ButtonGradients.apply(remove,"support",padding="0",font="700 20pt 'Segoe UI'")
        remove.setEnabled(enabled and bool(value));remove.setVisible(bool(value))
        remove.clicked.connect(lambda:cls.remove(panel,name,index))
        from .dcm_editor import DcmEditor
        editor=QPushButton();editor.setIcon(DcmEditor.icon());editor.setIconSize(QSize(18,18));editor.setFixedWidth(32)
        editor.setToolTip("DCM im Editor öffnen");ButtonGradients.apply(editor,"#fca5a5")
        editor.setEnabled(enabled and bool(value));editor.setVisible(bool(value))
        editor.clicked.connect(lambda:cls.open_editor(panel,edit))
        row._remove=remove;row._editor=editor
        layout.addWidget(remove);layout.addWidget(edit,1);layout.addWidget(editor);layout.addWidget(browse)
        section=panel._sections[name];section["layout"].addWidget(row);section["edits"].append(edit);section["buttons"].append(browse)

    @classmethod
    def open_editor(cls,panel,edit):
        from .dcm_editor import DcmEditor
        setup=getattr(panel._owner,"_setup_control",{}).get("selected")
        if setup:DcmEditor.open(edit.text(),setup,panel._owner)

    @classmethod
    def style_file(cls,edit,index,value):
        if value.strip():
            color="#fef3c7" if index==0 else "#ccfbf1"
            edit.setStyleSheet(f"QLineEdit {{background:{color}; color:#172554; border:1px solid #64748b; padding:5px;}}")
        else:
            color="#facc15" if index==0 else "#b59b00"
            edit.setStyleSheet(f"QLineEdit {{placeholder-text-color:{color};}}")

    @classmethod
    def browse(cls,panel,name,index,edit):
        filename,_=QFileDialog.getOpenFileName(panel._owner,"DCM-Datei auswählen",str(cls.default_directory(panel,name)),"DCM-Dateien (*.dcm *.DCM)")
        if filename:cls.selection_progress(panel,filename,lambda:cls.change(panel,name,index,filename))

    @classmethod
    def selection_progress(cls,panel,filename,apply_selection):
        from ..silEinrichten import SilEinrichten
        progress,body,animation=SilEinrichten.create_progress_card(
            "Dateiauswahl wird eingelesen",
            Path(filename).name+"\nDie Auswahl wird vorgemerkt. Mit Flashen nach Silver übertragen.")
        progress.setParent(panel._owner,Qt.WindowType.Dialog)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        for button in progress.findChildren(QPushButton):button.hide()
        progress.reject=lambda:None
        progress.closeEvent=lambda event:event.ignore()
        def finish():
            error=None
            try:apply_selection()
            except Exception as caught:error=str(caught)
            finally:
                animation.stop();progress.accept();progress.deleteLater()
            if error:Dialogs.message("Dateiauswahl nicht übernommen",error,panel._owner)
        animation.start();progress.show();Dialogs.foreground(progress)
        # Return to the GUI event loop so the wait window is painted first.
        QTimer.singleShot(50,finish)

    @classmethod
    def default_directory(cls,panel,name):
        entry=panel._entries.get(name,{})
        selected=getattr(panel._owner,"_setup_control",{}).get("selected")
        root=Path(selected).parent if selected else Path.cwd()
        sfu=Path(entry.get("path",name).replace("\\","/"))
        folder=(sfu if sfu.is_absolute() else root/sfu).parent
        for relative in ("Config/Datenstand","GeneralConfig/Datenstand"):
            candidate=folder/relative
            if candidate.is_dir():return candidate
        return folder/"Config/Datenstand"

    @classmethod
    def values(cls,panel,name):
        values=[edit.text().strip() for edit in panel._sections[name]["edits"]]
        if values and not values[0]:return [""]+[value for value in values[1:] if value]
        return [value for value in values if value]

    @classmethod
    def change(cls,panel,name,index,value):
        selected=getattr(panel._owner,"_setup_control",{}).get("selected")
        value=SilverParameterFiles.display_path(value,selected)
        existing=panel._entries.get(name,{}).get("files",[])
        if value==(existing[index] if index<len(existing) else ""):return
        if value and Path(value).suffix.lower()!=".dcm":
            Dialogs.message("DCM-Datei erforderlich","Bitte eine Datei mit der Endung .dcm auswählen.",panel._owner)
            panel._sections[name]["edits"][index].setText(existing[index] if index<len(existing) else "")
            return
        names=list(SilverParameterFiles.TARGETS) if panel._grouped.isChecked() else [name]
        if any(target not in panel._entries for target in names):
            Dialogs.message("SFU nicht vorhanden","Gruppieren benötigt Master und Slave im verbundenen Setup.",panel._owner);return
        changes={}
        for target in names:
            files=list(panel._entries[target]["files"])
            while len(files)<=index:files.append("")
            files[index]=value
            changes[target]=([""]+[item for item in files[1:] if item]) if files and not files[0] else [item for item in files if item]
        # Reflect the extra empty row and grouped edits immediately.
        updated={key:{**entry,"files":changes.get(key,entry["files"])} for key,entry in panel._entries.items()}
        panel._dirty.update(names)
        cls.stage(panel,updated)
        # Stage only. SFU changes may trigger loading inside Silver, so never
        # contact the API until the user explicitly presses Flashen.

    @classmethod
    def remove(cls,panel,name,index):
        names=list(SilverParameterFiles.TARGETS) if panel._grouped.isChecked() else [name]
        if any(target not in panel._entries for target in names):
            Dialogs.message("SFU nicht vorhanden","Gruppieren benötigt Master und Slave im verbundenen Setup.",panel._owner);return
        updated={key:{**entry,"files":list(entry["files"])} for key,entry in panel._entries.items()}
        for target in names:
            if index<len(updated[target]["files"]):
                if index==0:updated[target]["files"][0]=""
                else:del updated[target]["files"][index]
        panel._dirty.update(names)
        cls.stage(panel,updated)

    @classmethod
    def stage(cls,panel,entries):
        panel._entries=entries
        # Keep the Apply buttons alive when editingFinished fires on a button click.
        for name,entry in entries.items():
            section=panel._sections[name];values=entry["files"]+[""]
            while len(section["edits"])<len(values):
                index=len(section["edits"]);cls.add_row(panel,name,index,"",True)
            while len(section["edits"])>len(values):
                section["edits"].pop();section["buttons"].pop()
                section["layout"].takeAt(section["layout"].count()-1).widget().deleteLater()
            for index,(edit,value) in enumerate(zip(section["edits"],values)):
                edit.setText(value);edit.setToolTip(value)
                edit.setPlaceholderText("Haupt-DCM-Datei laden" if index==0 else "Weitere DCM-Datei laden ....")
                cls.style_file(edit,index,value)
                remove=edit.parentWidget()._remove
                remove.setVisible(bool(value));remove.setEnabled(bool(value))
                editor=edit.parentWidget()._editor;editor.setVisible(bool(value));editor.setEnabled(bool(value))
        cls.fit_lists(panel)

    @classmethod
    def changed_sides(cls,panel):
        return {name for name,entry in panel._entries.items()
                if cls.values(panel,name)!=panel._baseline[name]["files"] or
                panel._sections[name]["variant"].text()!=panel._baseline[name].get("variant","")}

    @classmethod
    def mirror_pending(cls,panel,payload,source):
        from difflib import SequenceMatcher
        baseline=panel._baseline[source]
        operations=SequenceMatcher(a=baseline["files"],b=payload[source]["files"],autojunk=False).get_opcodes()
        for target in set(payload)-{source}:
            files=list(payload[target]["files"])
            for tag,i,j,k,l in reversed(operations):
                replacement=payload[source]["files"][k:l]
                if tag=="insert" and files[i:i+len(replacement)]==replacement:continue
                if tag!="equal":files[i:j]=replacement
            payload[target]["files"]=files
            if payload[source]["variant"]!=baseline.get("variant",""):
                payload[target]["variant"]=payload[source]["variant"]

    @classmethod
    def grouping_changed(cls,panel,checked):
        if not checked or not panel._entries:return
        names=set(SilverParameterFiles.TARGETS)
        if not names.issubset(panel._entries):return
        dirty=cls.changed_sides(panel)
        if len(dirty)!=1:return
        source=next(iter(dirty))
        payload={name:{"files":cls.values(panel,name),"variant":panel._sections[name]["variant"].text()} for name in names}
        cls.mirror_pending(panel,payload,source)
        import copy
        entries=copy.deepcopy(panel._entries)
        selected=getattr(panel._owner,"_setup_control",{}).get("selected")
        for name,values in payload.items():
            entries[name]["files"]=values["files"]
            if "variant" in entries[name] or values["variant"]:entries[name]["variant"]=values["variant"]
            cls.variant_display(panel._sections[name],entries[name],selected)
        cls.stage(panel,entries)
        panel._dirty=cls.changed_sides(panel)

    @classmethod
    def apply(cls,panel,name=None):
        dirty=cls.changed_sides(panel)
        if not dirty:
            Dialogs.message("Keine Änderungen","Es sind keine Änderungen zum Flashen vorgemerkt.",panel._owner);return
        grouped=panel._grouped.isChecked()
        names=set(SilverParameterFiles.TARGETS) if grouped else dirty
        if any(target not in panel._entries for target in names):
            Dialogs.message("SFU nicht vorhanden","Gruppieren benötigt Master und Slave.",panel._owner);return
        payload={target:{"files":cls.values(panel,target),"variant":panel._sections[target]["variant"].text()} for target in names}
        if grouped and len(dirty)==1:cls.mirror_pending(panel,payload,next(iter(dirty)))
        if any(not entry["files"] or not entry["files"][0] for entry in payload.values()):
            Dialogs.message("Haupt-DCM fehlt","Bitte zuerst in der ersten Zeile eine Haupt-DCM-Datei auswählen.",panel._owner);return
        changes={target:(entry if "variant" in panel._entries[target] else entry["files"]) for target,entry in payload.items()}
        panel._dispatch("parameters_save",changes)
