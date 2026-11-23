"""Open DCM files with an explicitly selected and optionally remembered editor."""
from pathlib import Path
from PySide6.QtCore import QProcess,Qt,QSize
from PySide6.QtGui import QIcon,QPixmap,QPainter,QPen,QColor
from PySide6.QtWidgets import QFileDialog,QPushButton,QLineEdit,QCheckBox,QHBoxLayout,QDialog,QListWidget,QListWidgetItem
from ..core.config import Config
from ..ui.dialogs import Dialogs

class DcmEditor:
    @classmethod
    def icon(cls):
        pixmap=QPixmap(48,48);pixmap.fill(Qt.GlobalColor.transparent)
        painter=QPainter(pixmap);painter.setPen(QPen(QColor("#172554"),2))
        painter.drawRect(10,5,27,37);painter.drawLine(15,34,37,12);painter.drawLine(16,36,39,14)
        painter.end();return QIcon(pixmap)

    @classmethod
    def installed_editors(cls):
        import os,shutil,winreg
        editors=[];seen=set()
        known=(("Notepad++","notepad++.exe"),("Visual Studio Code","Code.exe"),("Windows Editor","notepad.exe"),("Sublime Text","sublime_text.exe"),("Notepad3","Notepad3.exe"),("Notepad2","Notepad2.exe"),("GVim","gvim.exe"),("UltraEdit","uedit64.exe"))
        for label,exe in known:
            candidates=[]
            found=shutil.which(exe)
            if found:candidates.append(found)
            for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
                for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
                    try:
                        with winreg.OpenKey(hive,"Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\"+exe,0,winreg.KEY_READ|view) as key:
                            candidates.append(os.path.expandvars(winreg.QueryValueEx(key,None)[0]).strip('"'))
                    except OSError:pass
            if exe=="notepad.exe":candidates.append(str(Path(os.environ.get("WINDIR","C:/Windows"))/"System32/notepad.exe"))
            if exe=="notepad++.exe":
                for env in ("ProgramFiles","ProgramFiles(x86)"):
                    if os.environ.get(env):candidates.append(str(Path(os.environ[env])/"Notepad++"/exe))
            if exe=="Code.exe" and os.environ.get("LOCALAPPDATA"):
                candidates.append(str(Path(os.environ["LOCALAPPDATA"])/"Programs/Microsoft VS Code/Code.exe"))
            for candidate in candidates:
                path=Path(candidate)
                normalized=os.path.normcase(str(path))
                if normalized not in seen and path.is_file():
                    seen.add(normalized);editors.append((label,str(path)));break
        return editors

    @classmethod
    def add_editor(cls,listing,label,path):
        item=QListWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,path);item.setToolTip(path)
        item.setSizeHint(QSize(0,42));listing.addItem(item)
        return item

    @classmethod
    def browse_editor(cls,dialog,listing):
        path,_=QFileDialog.getOpenFileName(dialog,"Editor auswählen","","Programme (*.exe)")
        if path:
            item=cls.add_editor(listing,Path(path).stem,path);listing.setCurrentItem(item)

    @classmethod
    def choose(cls,parent):
        dialog,footer,body=Dialogs.card("DCM-Editor auswählen","Wählen Sie einen installierten Texteditor aus der Liste.",parent)
        listing=QListWidget();listing.setObjectName("editorList")
        listing.setMinimumHeight(150)
        listing.setStyleSheet("QListWidget {background:#0f172a; color:#e2e8f0;} QListWidget::item {padding:6px;} QListWidget::item:hover, QListWidget::item:selected {background:#bbf7d0; color:#172554;}")
        for label,path in cls.installed_editors():cls.add_editor(listing,label,path)
        body.parentWidget().layout().insertWidget(body.parentWidget().layout().count()-1,listing)
        browse=QPushButton("Editor auswählen");browse.setStyleSheet("background:#bfdbfe; color:#172554; font-weight:700;")
        browse.clicked.connect(lambda:cls.browse_editor(dialog,listing));footer.addWidget(browse)
        remember=QCheckBox("Immer mit diesem Editor öffnen");remember.setObjectName("rememberEditor")
        remember.setStyleSheet("QCheckBox {background:#fed7aa; color:#172554; padding:8px; border-radius:4px; font-weight:700;} QCheckBox:checked {background:#99f6e4;}")
        from ..ui.checkboxes import Checkboxes
        Checkboxes.full_click(remember);footer.addWidget(remember)
        row=QHBoxLayout();cancel=QPushButton("Abbrechen");open_button=QPushButton("Öffnen");open_button.setEnabled(False)
        listing.currentItemChanged.connect(lambda current,previous:open_button.setEnabled(current is not None))
        listing.itemDoubleClicked.connect(lambda item:dialog.accept())
        cancel.clicked.connect(dialog.reject);open_button.clicked.connect(dialog.accept)
        row.addWidget(cancel);row.addWidget(open_button);footer.addLayout(row)
        dialog.resize(dialog.width(),min(620,dialog.maximumHeight()))
        if dialog.exec()!=QDialog.DialogCode.Accepted or listing.currentItem() is None:return None
        editor=Path(listing.currentItem().data(Qt.ItemDataRole.UserRole))
        if not editor.is_file() or editor.suffix.lower()!=".exe":raise ValueError("Der ausgewählte Editor wurde nicht gefunden.")
        if remember.isChecked():Config.set_state("DcmEditorPath",str(editor))
        return str(editor)

    @classmethod
    def open(cls,value,setup,parent):
        try:
            path=Path(value)
            if not path.is_absolute():path=Path(setup).parent/path
            from ..core.network_share import NetworkShare
            NetworkShare.require_file(path)
            if path.suffix.lower() not in (".dcm",".aed") or not path.is_file():raise ValueError("Die Datei wurde nicht gefunden: "+str(path))
            editor=Config.state().get("DcmEditorPath","")
            if not editor or not Path(editor).is_file():editor=cls.choose(parent)
            if not editor:return
            result=QProcess.startDetached(editor,[str(path)])
            if not (result[0] if isinstance(result,tuple) else result):raise RuntimeError("Der Editor konnte nicht gestartet werden.")
        except Exception as error:Dialogs.message("DCM konnte nicht geöffnet werden",str(error),parent)
