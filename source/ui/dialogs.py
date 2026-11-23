from pathlib import Path
import os
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QVBoxLayout, QScrollArea,
                              QWidget, QLabel, QSizePolicy, QPushButton)

class Dialogs:
    EXTRA_STYLE = """
        QFrame#card { background: #1e1e2e; }
        QLabel#brand { color: #40e0d0; font: 700 11pt 'Segoe UI'; }
        QLabel#heading { color: #facc15; font: 700 24pt 'Segoe UI'; }
        QLabel#body { color: #e2e8f0; font: 14pt 'Segoe UI'; }
        QFrame#track { background: #2a2a3e; border-radius: 7px; }
        QWidget#movingBar { background: #22c55e; border-radius: 7px; }
        QPushButton { background: #2a2a3e; color: #e2e8f0; border: 1px solid #475569;
                      border-radius: 5px; padding: 10px 18px; font:700 13pt 'Segoe UI'; }
        QMessageBox QLabel {color:#e2e8f0; font:14pt 'Segoe UI';}
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
        for name in ("segoeui.ttf","segoeuib.ttf"):
            font=Path(os.environ.get("WINDIR","C:/Windows"))/"Fonts"/name
            if font.is_file():QFontDatabase.addApplicationFont(str(font))
        QApplication.instance().setFont(QFont("Segoe UI", 10))
        dialog = QDialog(parent)
        dialog.setWindowTitle("siLAssistent - " + title)
        dialog.setWindowIcon(Launcher.icon())
        dialog.setStyleSheet(cls.style())
        screen = QApplication.primaryScreen().availableGeometry()
        dialog.setMaximumSize(max(260, screen.width() - 24), max(180, screen.height() - 48))
        dialog.resize(min(760, screen.width() - 24), min(500, screen.height() - 48))
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
        from ..core.network_share import NetworkShare
        network=NetworkShare.is_error(description)
        if network:
            if getattr(cls,"_network_notice_open",False):return 0
            title="M286-Laufwerk nicht erreichbar"
            description=NetworkShare.explain(description)
        dialog, footer, body = cls.card(title, description, parent)
        heading=dialog.findChild(QLabel,"heading")
        lower=title.casefold()
        if any(word in lower for word in ("fehler","nicht","fehlgeschlagen","konnte")):
            heading.setStyleSheet("color:#fda4af; font:700 24pt 'Segoe UI';")
        elif any(word in lower for word in ("erfolgreich","installiert","aktiviert","lizenz vorhanden")):
            heading.setStyleSheet("color:#86efac; font:700 24pt 'Segoe UI';")
        if title == "Jira-Zugriff nicht möglich":
            heading.setStyleSheet("color:#ffffff; font:700 24pt 'Segoe UI';")
            if "HTTP 404" in description:cls.style_jira_404_notice(dialog,body)
        if title in ("M286-Setup erfolgreich geklont", "M286-Setup konnte nicht geklont werden"):
            cls.style_clone_result(dialog, body, title, description)
        if title.endswith(" Branch ist aktiviert."):
            body.setStyleSheet("font:14pt 'Segoe UI';")
        if branch_status is not None:
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setText(cls.branch_summary_html(description,branch_status,target_branch))
        if title == "Git User Lizenz – Checkout":
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setStyleSheet("color:#facc15; font:700 18pt 'Segoe UI';")
            body.setText('BITTE KLICKEN SIE IM BROWSER AUF DEN <span style="color:#0078d4;">CHECKOUT</span>-BUTTON.<br><br>DER ASSISTENT FÄHRT ANSCHLIESSEND AUTOMATISCH FORT.')
        if title == "Jira-Antrag – Rolle auswählen":
            cls.style_jira_role_notice(dialog,body)
        if network:
            body.setStyleSheet("color:#facc15; font:700 16pt 'Segoe UI';")
            dialog.resize(min(760,dialog.maximumWidth()),min(520,dialog.maximumHeight()))
        close = QPushButton("OK" if network or title in ("Git User Lizenz – Bestellung prüfen","Git User Lizenz – Checkout","Jira-Antrag – Rolle auswählen") else "Schließen")
        if title == "Jira-Antrag – Rolle auswählen":
            from .button_gradients import ButtonGradients
            ButtonGradients.apply(close,"#99f6e4",padding="10px 24px",font="700 14pt 'Segoe UI'")
            close.setMinimumWidth(155)
        close.clicked.connect(dialog.accept)
        footer.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        if network or title in ("Git User Lizenz vorhanden", "Git User Lizenz – Bestellung prüfen", "Git User Lizenz – Checkout", "Jira-Antrag – Rolle auswählen"):
            dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            QTimer.singleShot(0, lambda: cls.foreground(dialog))
        if network:cls._network_notice_open=True
        try:return dialog.exec()
        finally:
            if network:cls._network_notice_open=False

    @classmethod
    def style_jira_404_notice(cls,dialog,body):
        body.setText('Das Board ist nicht sichtbar oder nicht vorhanden (HTTP 404).')
        body.setStyleSheet("color:#e2e8f0; font:14pt 'Segoe UI';")
        layout=body.parentWidget().layout();index=layout.indexOf(body)+1
        for name,text,color,size,weight in (
            ('jira404Retry','Bitte probieren Sie es später erneut.','#f59e0b',18,700),
            ('jira404Delay','Die tatsächliche Freischaltung benötigt etwas Zeit.','#e2e8f0',15,400),
            ('jira404Support','Wenn Sie zu einem späteren Zeitpunkt weiterhin keinen Zugang haben, melden Sie sich bitte über den Support-Button beim Systemadministrator.','#f9a8d4',16,700)):
            label=QLabel(text);label.setObjectName(name);label.setWordWrap(True)
            label.setStyleSheet(f"color:{color}; font:{weight} {size}pt 'Segoe UI';")
            layout.insertWidget(index,label);index+=1
        dialog.resize(min(760,dialog.maximumWidth()),min(650,dialog.maximumHeight()))

    @classmethod
    def style_jira_role_notice(cls,dialog,body):
        body.setText("Die verfügbaren Jira-Rollen werden im Browser angezeigt.")
        body.setStyleSheet("color:#e2e8f0; font:14pt 'Segoe UI';")
        layout=body.parentWidget().layout();index=layout.indexOf(body)+1
        steps=(("ERFORDERLICHE ROLLE AUSWÄHLEN","Wählen Sie die passende Rolle für Ihre Arbeit aus.","#40e0d0"),
               ("ANTRAG SELBST ABSENDEN","Führen Sie den Antrag im Browser selbst zu Ende.","#86efac"),
               ("NACH DEM ANTRAG HIERHER ZURÜCKKEHREN","Nach dem Absenden: Kehren Sie zu diesem Jira-Fenster in siLAssistent zurück.","#ffffff"))
        for number,(title,description,color) in enumerate(steps,1):
            card=QFrame();card.setObjectName('jiraRoleStep'+str(number))
            card.setStyleSheet('QFrame#'+card.objectName()+' {background:#29293d; border:1px solid #475569; border-radius:6px;}')
            content=QVBoxLayout(card);content.setContentsMargins(18,16,18,16);content.setSpacing(10)
            heading=QLabel(str(number)+'  '+title);heading.setWordWrap(True)
            heading.setStyleSheet(f"border:0; background:transparent; color:{color}; font:700 15pt 'Segoe UI';")
            explanation=QLabel(description);explanation.setWordWrap(True)
            explanation.setStyleSheet("border:0; background:transparent; color:#f1f5f9; font:14pt 'Segoe UI';")
            if number==3:
                card.setStyleSheet('QFrame#jiraRoleStep3 {background:#183d43; border:2px solid #40e0d0; border-left:6px solid #40e0d0; border-radius:6px;}')
                heading.setStyleSheet("border:0; background:transparent; color:#ffffff; font:700 16pt 'Segoe UI';")
                explanation.setStyleSheet("border:0; background:transparent; color:#ffffff; font:700 14pt 'Segoe UI';")
            content.addWidget(heading);content.addWidget(explanation)
            layout.insertWidget(index,card);index+=1
        note=QLabel('Mit OK wechseln Sie direkt zur geöffneten Browserseite.');note.setWordWrap(True)
        note.setStyleSheet("color:#cbd5e1; font:13pt 'Segoe UI';")
        layout.insertWidget(index,note)
        dialog.resize(min(800,dialog.maximumWidth()),min(780,dialog.maximumHeight()))

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
        heading.setStyleSheet("color:"+color+"; font:700 24pt 'Segoe UI';")
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

    @classmethod
    def confirm_branch_discard(cls,active,target,repositories,parent=None):
        import html
        from PySide6.QtWidgets import QHBoxLayout
        from .button_gradients import ButtonGradients
        dialog,footer,body=cls.card("Branch wechseln?","Im aktiven Branch sind lokale Änderungen vorhanden:",parent)
        layout=body.parentWidget().layout();index=layout.indexOf(body)+1
        branch=QLabel(active);branch.setTextFormat(Qt.TextFormat.PlainText);branch.setWordWrap(True)
        branch.setStyleSheet("color:#40e0d0; background:#233049; border:1px solid #406c88; border-radius:6px; padding:12px 16px; font:700 19pt 'Segoe UI';")
        warning=QLabel("NICHT GESPEICHERTE ÄNDERUNGEN\nGEHEN BEIM FORTFAHREN VERLOREN.");warning.setWordWrap(True)
        warning.setStyleSheet("color:#fda4af; font:700 16pt 'Segoe UI';")
        info=QLabel('Mit „Weiter“ werden die lokalen Änderungen verworfen<br>und der Branch <span style="color:#86efac; font-weight:700;">'+html.escape(target)+'</span> aktiviert.')
        info.setTextFormat(Qt.TextFormat.RichText);info.setWordWrap(True);info.setStyleSheet("color:#e2e8f0; font:14pt 'Segoe UI';")
        details=QLabel("Versionierte Änderungen und nicht versionierte Dateien in den betroffenen Repositories werden verworfen.")
        details.setWordWrap(True);details.setStyleSheet("color:#cbd5e1; font:12pt 'Segoe UI';")
        labels=[branch,warning,info,details]
        if len(repositories)>1 or any(item["branch"]!=active for item in repositories):
            names=QLabel("<br>".join(html.escape(Path(item["path"]).name)+' :: <span style="color:#40e0d0;">'+html.escape(item["branch"])+"</span>" for item in repositories))
            names.setTextFormat(Qt.TextFormat.RichText);names.setWordWrap(True);names.setStyleSheet("font:12pt 'Segoe UI';");labels.append(names)
        for offset,label in enumerate(labels):layout.insertWidget(index+offset,label)
        row=QHBoxLayout();cancel=QPushButton("Abbrechen");proceed=QPushButton("Weiter")
        ButtonGradients.apply(cancel,"#2a2a3e",font="700 14pt 'Segoe UI'",padding="10px 22px")
        ButtonGradients.apply(proceed,"#99f6e4",font="700 14pt 'Segoe UI'",padding="10px 22px")
        cancel.setDefault(True);proceed.setAutoDefault(False)
        cancel.clicked.connect(dialog.reject);proceed.clicked.connect(dialog.accept)
        row.addWidget(cancel);row.addWidget(proceed);footer.addLayout(row)
        dialog.resize(min(760,dialog.maximumWidth()),min(620,dialog.maximumHeight()))
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True)
        QTimer.singleShot(0,lambda:cls.foreground(dialog))
        return dialog.exec()==QDialog.DialogCode.Accepted
