"""Compose an Outlook access request; never send automatically."""
import configparser
import re
from pathlib import Path
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QCheckBox, QDialogButtonBox, QMessageBox
from ..core.config import Config
from ..core import build_settings

class RepoRequest:
    @classmethod
    def read_support_mail(cls, path):
        parser=configparser.ConfigParser(interpolation=None)
        parser.read(Path(path),encoding="utf-8-sig")
        values=[value.strip() for section in parser.sections() for key,value in parser.items(section) if key.lower()=="supportmail"]
        if len(values)!=1 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",values[0]):
            raise ValueError("Update-INI benötigt genau eine gültige supportMail-Adresse.")
        return values[0]

    @classmethod
    def recipient(cls):
        from ..ui.support import Support
        return Support.recipient()

    @classmethod
    def open(cls, parent):
        try:
            recipient=cls.recipient()
        except (OSError,ValueError) as error:
            QMessageBox.warning(parent,"Supportadresse fehlt",str(error))
            return
        dialog=QDialog(parent)
        dialog.setWindowTitle("Zugriff auf Setup-Repo beantragen")
        dialog.setStyleSheet(dialog.styleSheet() + """
            QCheckBox::indicator {width:16px; height:16px; border:2px solid #f59e0b; border-radius:3px; background:#1e1e2e;}
            QCheckBox::indicator:checked {background:#f59e0b; border:2px solid #fbbf24;}
            QPushButton#sendRepoRequest {background:#99f6e4; color:#172554; font-weight:700; border:0; padding:8px 14px; border-radius:4px;}
            QPushButton#sendRepoRequest:hover {background:#ccfbf1;}
        """)
        from .git import GitTool
        user_id=GitTool.windows_user()["username"].upper()
        layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel("M286-SiL-Setup Zugriff für ::"))
        layout.addWidget(QLabel("User-ID :: " + user_id))
        layout.addSpacing(14)
        layout.addWidget(QLabel("Gewünschte Rolle auswählen:"))
        choices=[]
        for role in ("Anwender (User)","Entwickler (Developer)","Admin"):
            checkbox=QCheckBox(role)
            layout.addWidget(checkbox)
            choices.append(checkbox)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Antrag senden")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("sendRepoRequest")
        buttons.accepted.connect(lambda: cls.validate_roles(dialog,choices))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:
            return
        try:
            cls.compose(recipient,[(box.text(),box.isChecked()) for box in choices])
        except Exception:
            QMessageBox.warning(parent,"Outlook","Der Outlook-Entwurf konnte nicht geöffnet werden. Bitte Outlook prüfen.")

    @classmethod
    def validate_roles(cls, dialog, choices):
        if not any(choice.isChecked() for choice in choices):
            QMessageBox.warning(dialog,"Rolle auswählen","Bitte wählen Sie mindestens eine Rolle aus.")
            if choices:
                choices[0].setFocus()
            return False
        dialog.accept()
        return True

    @classmethod
    def compose(cls, recipient, roles):
        if not any(checked for role,checked in roles):
            raise ValueError("Bitte wählen Sie mindestens eine Rolle aus.")
        import win32com.client
        outlook=win32com.client.Dispatch("Outlook.Application")
        mail=outlook.CreateItem(0)
        mail.To=recipient
        mail.Subject="Antrag auf M286-SiL-Setup"
        from .git import GitTool
        user_id=GitTool.windows_user()["username"].upper()
        mail.Body="M286-SiL-Setup Zugriff für ::\r\nUser-ID :: " + user_id + "\r\n\r\n" + "\r\n".join(("[x] " if checked else "[ ] ")+role for role,checked in roles)
        mail.Display(False)
