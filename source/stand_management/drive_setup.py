"""LW-Setup einrichten und den gespeicherten lokalen Zielpfad anzeigen."""
from pathlib import Path
from ..core.config import Config


class DriveSetup:
    @classmethod
    def target(cls,selected):
        folder=Path(selected)
        simulate=folder if folder.name.casefold()=="simulate" else folder/"Simulate"
        return simulate/"SimFiles"

    @classmethod
    def open(cls,parent):
        from .setup_updates import SetupUpdates
        from ..ui.dialogs import Dialogs
        from PySide6.QtWidgets import QPushButton,QApplication,QDialog
        from PySide6.QtCore import QTimer,Qt
        current=Config.state()["DriveSetupLocalPath"]
        dialog,footer,body=Dialogs.card("Setup vom Laufwerk", "Lokales Setup ::\n"+(current or "Noch kein lokales Setup eingerichtet."),parent)
        body.setStyleSheet("color:#f59e0b; font:12pt 'Segoe UI';")
        new=QPushButton("Neu Einrichten")
        new.setStyleSheet("background:#99f6e4; color:#172554; font-weight:700;")
        close=QPushButton("Schließen")
        new.clicked.connect(lambda:cls.choose(dialog))
        close.clicked.connect(dialog.reject)
        footer.addWidget(new);footer.addWidget(close)
        available=QApplication.primaryScreen().availableGeometry()
        width=min(560,available.width()-24)
        body_height=max(0,body.heightForWidth(max(180,width-90)))
        height=min(max(500,body_height+380),available.height()-48)
        dialog.resize(width,height)
        dialog._drive_controls=(body,new)
        dialog._drive_was_busy=None
        dialog.keyPressEvent=lambda event:event.ignore() if event.key()==Qt.Key.Key_Escape else QDialog.keyPressEvent(dialog,event)
        timer=QTimer(dialog)
        timer.timeout.connect(lambda:cls.refresh(dialog))
        timer.start(150)
        cls.refresh(dialog)
        QTimer.singleShot(0,lambda:SetupUpdates.watch(dialog,"drive"))
        dialog.exec()
        timer.stop()

    @classmethod
    def refresh(cls,dialog):
        from .setup_updates import SetupUpdates
        busy=bool(getattr(SetupUpdates,"_active",False))
        if dialog._drive_was_busy==busy:return
        dialog._drive_was_busy=busy
        body,new=dialog._drive_controls
        new.setEnabled(not busy)
        if not busy:
            current=Config.state()["DriveSetupLocalPath"]
            body.setText("Lokales Setup ::\n"+(current or "Noch kein lokales Setup eingerichtet."))
    
    @classmethod
    def choose(cls,parent):
        from .setup_updates import SetupUpdates
        from PySide6.QtWidgets import QFileDialog
        if getattr(SetupUpdates,"_active",False):return
        selected=QFileDialog.getExistingDirectory(parent,"Zielordner wählen – Setup wird unter Simulate/SimFiles eingerichtet")
        if not selected:return
        target=str(cls.target(selected))
        SetupUpdates._active=True
        SetupUpdates.spawn(parent,"drive","configure_drive",target=target)
