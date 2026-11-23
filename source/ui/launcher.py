"""AppliTools-style launcher; vendor APIs remain in backend packages."""
from pathlib import Path
import os
import queue
import logging
import threading
from PySide6.QtCore import QTimer, Qt, QSize
from PySide6.QtGui import QFontDatabase, QFont, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QLabel, QPushButton, QMessageBox, QFrame, QScrollArea,
                              QToolButton, QSizePolicy, QDialog, QDialogButtonBox)
from ..core.config import Config
from ..core.update import UpdateManager
from ..core.runtime import Runtime

class Launcher:
    _window = None
    _update_started = False
    _messages = queue.Queue()
    BG = "#1e1e2e"
    PANEL = "#2a2a3e"
    ACCENT = "#60a5fa"
    GREEN = "#22c55e"
    TEXT = "#e2e8f0"
    MUTED = "#94a3b8"
    STYLE = """
        QComboBox QAbstractItemView {selection-background-color:#bbf7d0; selection-color:#172554;}
        QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected {background:#bbf7d0; color:#172554;}

        QMainWindow, QWidget { background: #1e1e2e; color: #e2e8f0; font: 10pt 'Segoe UI'; }
        QScrollArea { border: 0; }
        QLabel#title { color: #facc15; font-size: 32pt; font-weight: 800; }
        QLabel#subtitle { color: #94a3b8; font-size: 9pt; }
        QFrame#accentSep { background: #60a5fa; border: 0; }
        QFrame#divider { background: #2a2a3e; border: 0; }
        QPushButton#setupButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #246c58, stop:1 #153c35);
            color: #ffffff; border: 1px solid #8ddcc0; border-top: 2px solid #a2fddd;
            border-radius: 6px; padding: 12px 24px; font: 700 11pt 'Segoe UI'; }
        QPushButton#setupButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2c8069, stop:1 #1c5046);
            color: #ffffff; }
        QPushButton#setupButton:pressed { background: #153c35; color: #ffffff; }
        QPushButton#setupButton:focus { border: 2px solid #a2fddd; }
        QToolButton { background: #2a2a3e; border: 0; border-radius: 4px;
            padding: 10px 8px; font-weight: 700; text-align: left; }
        QToolButton:hover { background: #353550; }
        QToolButton#standHeader { color: #f59e0b; }
        QToolButton#operationHeader { color: #22c55e; }
        QLabel#sectionHint { color: #94a3b8; padding: 14px 8px; font-size: 9pt; }
        QFrame#bottomBar { background: #2a2a3e; border-radius: 4px; }
        QFrame#bottomBar QLabel { background: transparent; }
        QLabel#suiteLabel { color: #40e0d0; font-size: 8pt; }
        QDialogButtonBox QPushButton { background: #2a2a3e; color: #e2e8f0;
            border: 1px solid #475569; padding: 8px 16px; border-radius: 4px; }
        QLabel#fieldLabel { color: #94a3b8; font-size: 9pt; }
    """

    @classmethod
    def icon(cls):
        from .button_frames import ButtonFrames
        ButtonFrames.install()
        from .icons import Icons
        return Icons.application()

    @classmethod
    def create(cls):
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
        QApplication.instance().setFont(QFont("Segoe UI", 10))
        window = QMainWindow()
        cls._window = window
        window.setObjectName("siLAssistentLauncher")
        window.setProperty("buttonFramePolicy","launcher")
        window.setWindowTitle(f"siLAssistent - Launcher  v {Config.version()}")
        window.setWindowIcon(cls.icon())
        QApplication.instance().setWindowIcon(cls.icon())
        available = QApplication.primaryScreen().availableGeometry()
        window.resize(min(600, available.width() - 24), min(760, available.height() - 48))
        window.setStyleSheet(cls.STYLE)
        central = QWidget()
        window.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(20, 18, 20, 10)
        outer.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        root = QVBoxLayout(content)
        root.setContentsMargins(12, 0, 12, 0)
        root.setSpacing(10)
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addStretch()
        mark = QLabel()
        mark.setObjectName("assistantMark")
        mark.setPixmap(cls.icon().pixmap(QSize(96, 96)))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setAccessibleName("Assistent")
        header.addWidget(mark)
        title = QLabel("siLAssistent")
        title.setObjectName("title")
        if available.width() < 620:
            title.setStyleSheet("font-size: 25pt;")
        header.addWidget(title)
        header.addStretch()
        root.addLayout(header)
        subtitle = QLabel("Tool-Sammlung für SiL-Themen")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(subtitle)
        line = QFrame()
        line.setObjectName("accentSep")
        line.setFixedHeight(2)
        root.addWidget(line)
        root.addSpacing(8)
        setup_row = QHBoxLayout()
        setup_row.addStretch()
        setup = QPushButton("SiL-Einrichten")
        setup.setObjectName("setupButton")
        setup.setProperty("suiteButtonFrame", True)
        setup.setMinimumHeight(44)
        setup.setMinimumWidth(240)
        setup.setCursor(Qt.CursorShape.PointingHandCursor)
        setup.clicked.connect(cls.show_setup)
        setup_row.addWidget(setup)
        setup_row.addStretch()
        root.addLayout(setup_row)
        root.addSpacing(8)
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        root.addWidget(divider)
        root.addSpacing(4)
        columns = QHBoxLayout()
        columns.setSpacing(10)
        columns.addWidget(cls.section("Stand-Management", "standHeader",
                          "", tools=(("Git", "gitTool", cls.open_git),
                                     ("Setup vom Laufwerk kopieren", "driveSetupTool", cls.open_drive_setup),
                                     ("Jira", "jiraTool", cls.open_jira))), 1)
        columns.addWidget(cls.section("Setup-Betrieb", "operationHeader", "",
                          tools=(("Setup-Ansteuerung","setupControlTool",cls.open_setup_control),)), 1)
        root.addLayout(columns)
        root.addStretch(1)
        footer = QFrame()
        footer.setObjectName("bottomBar")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 10, 14, 10)
        suite = QLabel("siLAssistent Suite\nTeam-Merkle RD/EIC")
        suite.setObjectName("suiteLabel")
        support_column = QVBoxLayout()
        support_column.setContentsMargins(0, 0, 0, 0)
        support_column.setSpacing(12)
        support=QPushButton("Support");support.setObjectName("supportButton")
        support.setProperty("suiteButtonFrame", True)
        from .icons import Icons
        support.setIcon(Icons.file_icon(Runtime.project_root()/"icons"/"Support.ico"))
        support.setIconSize(QSize(68,68));support.setCursor(Qt.CursorShape.PointingHandCursor)
        support.setMinimumSize(250,104)
        support.setStyleSheet("""
            QPushButton {
                background:qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #743b4d, stop:1 #382431);
                color:#ffffff; font:700 16pt 'Segoe UI'; padding:12px 18px;
                border:1px solid #ecc1cd; border-top:2px solid #f5d9e1; border-radius:7px;
            }
            QPushButton:hover {
                background:qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #87465b, stop:1 #4b2e40);
            }
            QPushButton:pressed {background:#382431;}
            QPushButton:focus {border:2px solid #f5d9e1;}
        """)
        support.setToolTip("Neue Supportnachricht in Outlook öffnen")
        from .support import Support
        support.clicked.connect(lambda:Support.open(window))
        support_column.addWidget(support, 0, Qt.AlignmentFlag.AlignLeft)
        support_column.addWidget(suite)
        footer_layout.addLayout(support_column)
        footer_layout.addStretch()
        user_config=QPushButton("Benutzer-Konfig")
        user_config.setObjectName("userConfigButton")
        user_config.setProperty("suiteButtonFrame", True)
        user_config.setCursor(Qt.CursorShape.PointingHandCursor)
        user_config.setStyleSheet("""
            QPushButton {
                background:qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #258d91, stop:1 #15535e);
                color:#ffffff; font-weight:700; padding:7px 10px;
                border:1px solid #89e5e4; border-top:2px solid #97fcfb; border-radius:6px;
            }
            QPushButton:hover {
                background:qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2aa0a5, stop:1 #1b6673);
            }
            QPushButton:pressed {background:#15535e;}
            QPushButton:focus {border:2px solid #97fcfb;}
        """)
        from .user_config import UserConfigDialog
        user_config.clicked.connect(lambda:UserConfigDialog.open(window))
        footer_layout.addWidget(user_config, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        outer.addWidget(footer, 0)
        cls._last_update_status = ""
        cls._silver_prompted = False
        cls._timer = QTimer(window)
        cls._timer.timeout.connect(cls.poll)
        cls._timer.start(150)
        return window

    @classmethod
    def section(cls, title, object_name, description, tools=()):
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        button = QToolButton()
        button.setObjectName(object_name)
        button.setText(title)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setArrowType(Qt.ArrowType.RightArrow)
        button.setCheckable(True)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(button)
        body = QWidget()
        body.setObjectName(object_name + "Content")
        content = QVBoxLayout(body)
        content.setContentsMargins(4, 4, 4, 4)
        content.setSpacing(4)
        if tools:
            for label, name, callback in tools:
                tool = QPushButton(label)
                tool.setObjectName(name)
                tool.setMinimumHeight(36)
                tool.setCursor(Qt.CursorShape.PointingHandCursor)
                color, hover = {"gitTool": ("#f59e0b", "#fbbf24"),
                                "driveSetupTool": ("#40e0d0", "#7cece1"),
                                "setupControlTool": ("#86efac", "#bbf7d0"),
                                "jiraTool": ("#facc15", "#fde047")}.get(name, ("#a78bfa", "#c4b5fd"))
                tool.setStyleSheet(f"QPushButton {{background:{color};color:#0f172a;border:0;"
                                  "border-radius:4px;padding:8px 12px;font-weight:700;text-align:left;}"
                                  f"QPushButton:hover {{background:{hover};}}")
                tool.clicked.connect(callback)
                content.addWidget(tool)
        else:
            hint = QLabel(description)
            hint.setObjectName("sectionHint")
            hint.setWordWrap(True)
            content.addWidget(hint)
        body.setVisible(False)
        button.toggled.connect(lambda checked: cls.toggle_section(button, body, checked))
        layout.addWidget(body)
        layout.addStretch()
        return section

    @classmethod
    def toggle_section(cls, button, body, checked):
        body.setVisible(checked)
        button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    @classmethod
    def show_setup(cls):
        from ..silEinrichten import SilEinrichten
        try:
            return SilEinrichten.launch()
        except Exception as error:
            from .dialogs import Dialogs
            Dialogs.message("SiL-Einrichten", f"SiL-Einrichten konnte nicht gestartet werden: {error}", cls._window)

    @classmethod
    def open_git(cls):
        from ..stand_management import GitTool
        window=GitTool.open(cls._window)
        from ..stand_management.setup_updates import SetupUpdates
        SetupUpdates.watch(window,"git")
        return window

    @classmethod
    def open_drive_setup(cls):
        from ..stand_management.drive_setup import DriveSetup
        DriveSetup.open(cls._window)

    @classmethod
    def open_setup_control(cls):
        from ..setup_operation.setup_control import SetupControl
        return SetupControl.open(cls._window)

    @classmethod
    def open_jira(cls):
        from ..stand_management import JiraTool
        return JiraTool.open(cls._window)

    @classmethod
    def update_status(cls, text):
        """Keep update diagnostics out of the launcher layout."""
        cls._last_update_status = text

    @classmethod
    def check_updates(cls):
        if getattr(cls, "_checking", False):
            return
        config = Config.load()
        cls._share_notice_shown=False
        cls._update_check_notice_shown=False
        cls.start_silver_check(config["update_ini_path"])
        if not config["update_ini_path"]:
            cls.update_status("Noch kein Laufwerk-Updatepfad konfiguriert (siLAssistent.ini).")
            return
        cls._checking = True
        cls.update_status("Versionsprüfung …")
        threading.Thread(target=cls.update_worker, args=(config["update_ini_path"],), daemon=True).start()

    @classmethod
    def update_worker(cls, path):
        try:
            release = UpdateManager.check(path, Config.version())
            cls._messages.put(("release", release))
        except Exception as error:
            cls._messages.put(("check_error", str(error)))

    @classmethod
    def start_silver_check(cls, path):
        if getattr(cls, "_silver_checking", False):
            return
        cls._silver_checking = True
        threading.Thread(target=cls.silver_check_worker, args=(path,), daemon=True).start()

    @classmethod
    def silver_check_worker(cls, path):
        from ..silver.probe import SilverProbe
        try:
            SilverProbe.collect(path, cls._messages)
        except Exception as error:
            cls._messages.put(("check_error", "Silver: " + str(error)))
        finally:
            cls._silver_checking = False

    @classmethod
    def stage_worker(cls, release, cancelled=None):
        try:
            cls._messages.put(("installer", str(UpdateManager.stage(release,progress=lambda text,value:cls._messages.put(("update_progress",(text,value))),cancelled=cancelled))))
        except Exception as error:
            cls._messages.put(("update_cancelled",None) if cancelled is not None and cancelled.is_set() else ("install_error",str(error)))

    @classmethod
    def poll(cls):
        try:
            kind, data = cls._messages.get_nowait()
            while kind=="update_progress":
                cls.update_progress(*data)
                kind,data=cls._messages.get_nowait()
        except queue.Empty:
            return
        cls._checking = False
        if kind == "update_cancelled":return
        if kind == "check_error":
            # An unavailable share must not insert technical errors into the launcher.
            cls.update_status(f"Updateprüfung nicht möglich: {data}")
            logging.getLogger("siLAssistent").info("Background update check unavailable: %s", data)
            from ..core.network_share import NetworkShare
            if NetworkShare.is_error(data) and not getattr(cls,"_share_notice_shown",False):
                cls._share_notice_shown=True
                from .dialogs import Dialogs
                Dialogs.message("M286-Laufwerk nicht erreichbar",str(data),cls._window)
        elif kind == "install_error":
            cls.finish_update_progress()
            cls.update_status(f"Updateinstallation nicht möglich: {data}")
            if cls._update_started:
                cls._update_started=False
                from .update_recovery import UpdateRecovery
                UpdateRecovery.notice(cls._window,error=data,release=getattr(cls,"_update_release",None))
        elif kind == "silver_local":
            cls._detected_silver_version = data["version"]
        elif kind == "silver_release":
            cls.offer_silver_update(data)
        elif kind == "installer":
            try:
                cls.update_progress("Geöffnete Bereiche werden geschlossen …",None)
                if not cls.close_tools():raise RuntimeError("Bitte laufende Vorgänge abschließen und das Update erneut starten.")
                from ..stand_management.jira import JiraTool
                JiraTool.shutdown()
                UpdateManager.launch_after_exit(data)
                cls._timer.stop()
                cls.finish_update_progress()
                cls._window._update_exit=True
                QApplication.instance().quit()
            except Exception as error:
                cls.finish_update_progress()
                cls.update_status(str(error))
                if cls._update_started:
                    cls._update_started=False
                    from .update_recovery import UpdateRecovery
                    UpdateRecovery.notice(cls._window,error=error,release=getattr(cls,"_update_release",None))
        elif data["available"]:
            from .update_recovery import UpdateRecovery
            cls._update_release=data
            cls._update_started=False
            answer=UpdateRecovery.offer(cls._window,data)
            if answer == QMessageBox.StandardButton.Yes:
                cls._update_started=True
                cls._update_cancel=threading.Event()
                cls.update_status("Update wird lokal vorbereitet und geprüft …")
                cls.update_progress("Update ... Verbindung zum Laufwerk wird hergestellt …",None)
                cls._checking = True
                try:threading.Thread(target=cls.stage_worker, args=(data,cls._update_cancel), daemon=True).start()
                except Exception as error:cls._messages.put(("install_error",str(error)))
            else:
                cls.update_status("Update wurde zurückgestellt.")
        else:
            cls.update_status("siLAssistent ist aktuell.")

    @classmethod
    def update_progress(cls,text,value):
        from .progress import ProgressWindow
        if getattr(cls,"_update_progress",None) is None:
            cls._update_progress=ProgressWindow.create("update",cls._window)
        ProgressWindow.stage(cls._update_progress,text,value)

    @classmethod
    def finish_update_progress(cls):
        from .progress import ProgressWindow
        ProgressWindow.finish(getattr(cls,"_update_progress",None))
        cls._update_progress=None

    @classmethod
    def offer_silver_update(cls, release):
        if not release["available"] or getattr(cls, "_silver_prompted", False):
            return
        cls._silver_prompted = True
        from ..silEinrichten import SilEinrichten
        import socket
        description = (f"Rechner: {socket.gethostname()}\nInstalliert :: {release['installed_version']}\nVerfügbar :: {release['version']}\n\n"
                       "Möchten Sie Silver aktualisieren?\n"
                       "Mit Ja wird zuerst die vorhandene Silver-Version deinstalliert und anschließend "
                       "die neue Version installiert. Bitte laufende Silver-Simulationen vorher schließen.")
        if not SilEinrichten.ask_question("Silver-Update vorhanden", description):
            return
        try:
            SilEinrichten.launch(silver_update=True, installer=release["installer_path"],
                                 previous_version=release["installed_version"], target_version=release["version"],
                                 uninstall_target=release["target_locator"])
        except Exception as error:
            from .dialogs import Dialogs
            Dialogs.message("Silver-Update nicht gestartet", str(error), cls._window)

    @classmethod
    def foreground_close_prompt(cls, dialog):
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        if os.name == "nt":
            from ..silEinrichten import SilverInstallation
            SilverInstallation.show_wizard(int(dialog.winId()))

    @classmethod
    def close_tools(cls):
        from ..stand_management.setup_updates import SetupUpdates
        if getattr(SetupUpdates,"_active",False) and getattr(SetupUpdates,"_state",{}).get("operation")!="check":
            QMessageBox.information(cls._window,"Setup-Update läuft","Bitte das laufende Setup-Update vor dem Beenden abwarten.")
            return False
        tools = [tool for tool in QApplication.topLevelWidgets()
                 if tool.property("siLAssistentTool") and tool.isVisible()]
        for tool in tools:
            if getattr(tool, "_git", {}).get("busy", False):
                tool.showNormal()
                tool.raise_()
                tool.activateWindow()
                tool.statusBar().showMessage("Bitte den laufenden Git-Vorgang vor dem Beenden abwarten.")
                return False
        for tool in tools:
            if not tool.close():
                return False
        return True

    @classmethod
    def close_event(cls, window, event):
        if getattr(window,"_update_exit",False) is True:
            event.accept()
            return
        if getattr(window, "_close_prompt", None) is not None:
            cls.foreground_close_prompt(window._close_prompt)
            event.ignore()
            return
        window.showNormal()
        window.raise_()
        window.activateWindow()
        box = QMessageBox(window)
        box.setWindowTitle("siLAssistent beenden")
        box.setText("Wollen Sie siLAssistent beenden?")
        box.setIcon(QMessageBox.Icon.Question)
        yes = box.addButton("Yes", QMessageBox.ButtonRole.YesRole)
        no = box.addButton("No", QMessageBox.ButtonRole.NoRole)
        no.setObjectName("exitNo")
        no.setProperty("suiteButtonFrame",True)
        box.setStyleSheet(box.styleSheet()+" QPushButton#exitNo {border:2px solid #40e0d0; border-radius:5px; padding:6px 24px;}")
        box.setDefaultButton(no)
        box.setEscapeButton(no)
        box.setWindowModality(Qt.WindowModality.ApplicationModal)
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        window._close_prompt = box
        try:
            QTimer.singleShot(0, lambda: cls.foreground_close_prompt(box))
            box.exec()
            if box.clickedButton() is yes and cls.close_tools():
                from ..stand_management.jira import JiraTool
                JiraTool.shutdown()
                cls._timer.stop()
                event.accept()
            else:
                event.ignore()
        finally:
            window._close_prompt = None
            box.deleteLater()

    @classmethod
    def startup(cls):
        from ..stand_management.git_incoming_updates import GitIncomingUpdates
        GitIncomingUpdates.check(cls._window)
        if cls._startup_updates:
            cls.check_updates()
        else:
            cls.start_silver_check(None)

    @classmethod
    def run(cls, check_updates=True, progress=None):
        app = QApplication.instance() or QApplication([])
        app.setStyle("Fusion")
        window = cls.create()
        window.closeEvent = lambda event: cls.close_event(window, event)
        window.show()
        if progress is not None:
            from .progress import ProgressWindow
            ProgressWindow.stage(progress,"Bereit",100,paint=True)
            ProgressWindow.finish(progress)
        cls._startup_updates = check_updates
        QTimer.singleShot(700, cls.startup)
        return app.exec()
