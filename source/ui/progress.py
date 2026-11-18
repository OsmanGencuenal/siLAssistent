"""Shared siLAssistent progress window for startup and software updates."""
from pathlib import Path
from PySide6.QtCore import Qt,QEventLoop
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QProgressBar
from PySide6.QtGui import QFontDatabase
from ..core.runtime import Runtime

class ProgressWindow:
    @classmethod
    def create(cls,kind,parent=None):
        font=Path("C:/Windows/Fonts/segoeui.ttf")
        if font.is_file():QFontDatabase.addApplicationFont(str(font))
        dialog=QDialog(parent);dialog.setObjectName("siLProgress")
        dialog.setWindowFlags(Qt.WindowType.Dialog|Qt.WindowType.FramelessWindowHint)
        dialog.setWindowModality(Qt.WindowModality.WindowModal if parent else Qt.WindowModality.NonModal)
        dialog.reject=lambda:None;dialog.closeEvent=lambda event:event.ignore()
        update=kind=="update";accent="#f59e0b" if update else "#60a5fa"
        title="siLAssistent Update" if update else "siLAssistent"
        dialog.setWindowTitle(title)
        dialog.setStyleSheet("QDialog#siLProgress {background:#1e1e2e; border:1px solid #475569;} QLabel {background:transparent; color:#e2e8f0; font:12pt 'Segoe UI';} QProgressBar {background:#323248; border:0; border-radius:4px; min-height:16px; max-height:16px;} QProgressBar::chunk {background:"+accent+"; border-radius:4px;}")
        layout=QVBoxLayout(dialog);layout.setContentsMargins(32,25,32,25);layout.setSpacing(12)
        heading=QHBoxLayout();heading.addStretch()
        from .icons import Icons
        icon=Icons.file_icon(Runtime.project_root()/"icons/Support.ico")
        image=QLabel();image.setPixmap(icon.pixmap(52,52));heading.addWidget(image)
        label=QLabel(title);label.setStyleSheet("color:"+accent+"; font:700 28pt 'Segoe UI';")
        heading.addWidget(label);heading.addStretch();layout.addLayout(heading)
        subtitle=QLabel("Installation wird vorbereitet …" if update else "Anwendung wird vorbereitet …")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(subtitle)
        status=QLabel();status.setWordWrap(True);status.setStyleSheet("color:#40e0d0; font:12pt 'Segoe UI';")
        bar=QProgressBar();bar.setTextVisible(False)
        percent=QLabel();percent.setAlignment(Qt.AlignmentFlag.AlignRight)
        percent.setStyleSheet("color:#94a3b8; font:11pt 'Segoe UI';")
        for widget in (status,bar,percent):layout.addWidget(widget)
        dialog._status=status;dialog._bar=bar;dialog._percent=percent
        available=QApplication.primaryScreen().availableGeometry()
        dialog.resize(min(720,available.width()-40),250)
        dialog.move(available.center()-dialog.rect().center())
        return dialog

    @classmethod
    def stage(cls,dialog,text,value,paint=False):
        dialog._status.setText(text);dialog._bar.setRange(0,0 if value is None else 100)
        if value is not None:dialog._bar.setValue(value)
        dialog._percent.setText("Bitte warten …" if value is None else str(value)+" %")
        dialog.show()
        if paint:QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    @classmethod
    def finish(cls,dialog):
        if dialog is not None:dialog.hide();dialog.deleteLater()
