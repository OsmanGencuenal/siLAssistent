"""Launcher dialog for portable user settings."""
from pathlib import Path
from PySide6.QtWidgets import QPushButton,QFileDialog
from ..core.user_config import UserConfig
from .dialogs import Dialogs


class UserConfigDialog:
    @classmethod
    def open(cls,parent):
        dialog,footer,body=Dialogs.card("Benutzer-Konfig","Benutzer-Einstellungen exportieren oder importieren.",parent)
        export=QPushButton("Export");import_button=QPushButton("Import")
        export.clicked.connect(lambda:cls.export(dialog))
        import_button.clicked.connect(lambda:cls.import_file(dialog))
        footer.addWidget(export);footer.addWidget(import_button)
        dialog.exec()

    @classmethod
    def export(cls,parent):
        from ..stand_management.git import GitTool
        try:
            user_id=GitTool.windows_user()["username"].upper()
            filename,_=QFileDialog.getSaveFileName(parent,"Benutzer-Konfiguration exportieren",str(Path.home()/(user_id+".ini")),"INI-Dateien (*.ini)")
            if not filename:return
            target=UserConfig.export(filename)
            Dialogs.message("Benutzer-Konfig exportiert","Gespeichert unter ::\n"+str(target),parent)
        except Exception as error:
            Dialogs.message("Export nicht abgeschlossen",str(error),parent)

    @classmethod
    def import_file(cls,parent):
        filename,_=QFileDialog.getOpenFileName(parent,"Benutzer-Konfiguration importieren",str(Path.home()),"INI-Dateien (*.ini)")
        if not filename:return
        try:
            count=UserConfig.import_file(filename)
            Dialogs.message("Benutzer-Konfig importiert",str(count)+" Benutzer-Einstellungen wurden übernommen.",parent)
        except Exception as error:
            Dialogs.message("Import nicht abgeschlossen",str(error),parent)
