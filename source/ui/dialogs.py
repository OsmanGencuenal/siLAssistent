from pathlib import Path
import os
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QVBoxLayout, QScrollArea,
                              QWidget, QLabel, QSizePolicy, QPushButton)

class Dialogs:
    EXTRA_STYLE = """
        QFrame#card { background: #1e1e2e; }
        QLabel#brand { color: #facc15; font: 700 10pt 'Segoe UI'; }
        QLabel#heading { color: #e2e8f0; font: 700 18pt 'Segoe UI'; }
        QLabel#body { color: #cbd5e1; font: 10pt 'Segoe UI'; }
        QFrame#track { background: #2a2a3e; border-radius: 7px; }
        QWidget#movingBar { background: #22c55e; border-radius: 7px; }
        QPushButton { background: #2a2a3e; color: #e2e8f0; border: 1px solid #475569;
                      border-radius: 4px; padding: 8px 16px; }
        QPushButton:hover { background: #353550; }
        QPushButton#primary { background: #60a5fa; color: #0f172a; border: 0; font-weight: 700; }
    """

    @classmethod
    def style(cls):
        from .launcher import Launcher
        return Launcher.STYLE + cls.EXTRA_STYLE

    @classmethod
    def card(cls, title, description, parent=None):
        from .launcher import Launcher
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
        QApplication.instance().setFont(QFont("Segoe UI", 10))
        dialog = QDialog(parent)
        dialog.setWindowTitle("siLAssistent - " + title)
        dialog.setWindowIcon(Launcher.icon())
        dialog.setStyleSheet(cls.style())
        screen = QApplication.primaryScreen().availableGeometry()
        dialog.setMaximumSize(max(260, screen.width() - 24), max(180, screen.height() - 48))
        dialog.resize(min(560, screen.width() - 24), min(400, screen.height() - 48))
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(16, 16, 16, 16)
        card = QFrame()
        card.setObjectName("card")
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        message = QVBoxLayout(content)
        message.setSpacing(14)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        brand = QLabel("siLAssistent")
        brand.setObjectName("brand")
        message.addWidget(brand)
        heading = QLabel(title)
        heading.setObjectName("heading")
        heading.setWordWrap(True)
        heading.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        message.addWidget(heading)
        body = QLabel(description)
        body.setObjectName("body")
        body.setWordWrap(True)
        body.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        body.setTextFormat(Qt.TextFormat.PlainText)
        message.addWidget(body)
        message.addStretch()
        footer = QVBoxLayout()
        footer.setSpacing(10)
        layout.addLayout(footer)
        return dialog, footer, body

    @classmethod
    def message(cls, title, description, parent=None, branch_status=None, target_branch=None):
        dialog, footer, body = cls.card(title, description, parent)
        if title in ("M286-Setup erfolgreich geklont", "M286-Setup konnte nicht geklont werden"):
            cls.style_clone_result(dialog, body, title, description)
        if title.endswith(" Branch ist aktiviert."):
            body.setStyleSheet("font:14pt 'Segoe UI';")
        if branch_status is not None:
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setText(cls.branch_summary_html(description,branch_status,target_branch))
        close = QPushButton("Schließen")
        close.clicked.connect(dialog.accept)
        footer.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        if title == "Git User Lizenz vorhanden":
            dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            QTimer.singleShot(0, lambda: cls.foreground(dialog))
        return dialog.exec()

    @classmethod
    def branch_summary_html(cls, description, entries, target):
        import html
        lines=[html.escape(description), ""]
        for entry in entries:
            text="• "+html.escape(entry["name"])+" :: "+html.escape(entry["branch"])
            if entry["branch"]==target:
                text='<span style="color:#facc15; font-weight:700;">'+text+'</span>'
            lines.append(text)
        return "<br>".join(lines)

    @classmethod
    def style_clone_result(cls, dialog, body, title, description):
        import html
        successful = title == "M286-Setup erfolgreich geklont"
        color = "#22c55e" if successful else "#ef4444"
        symbol = "\u2713" if successful else "\u2717"
        heading = dialog.findChild(QLabel, "heading")
        heading.setTextFormat(Qt.TextFormat.RichText)
        heading.setText('<span style="font-family:Segoe UI Symbol;">' + symbol + '</span> ' + html.escape(title))
        heading.setStyleSheet("color:"+color+"; font:700 22pt 'Segoe UI';")
        body.setStyleSheet("font:14pt 'Segoe UI';")
        if successful:
            lines = description.splitlines()
            path = lines[1] if len(lines)>1 else ""
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setText('Repo wurde unter ::<br><span style="color:#f59e0b; font-size:16pt; font-weight:700;">'
                         + html.escape(path) + '</span><br><br>erfolgreich geklont.')
        dialog.resize(dialog.width(), min(480,dialog.maximumHeight()))

    @classmethod
    def foreground(cls, dialog):
        from ..silEinrichten import SilEinrichten
        SilEinrichten.foreground_dialog(dialog)
