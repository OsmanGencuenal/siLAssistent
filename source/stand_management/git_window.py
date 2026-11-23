"""Non-modal Git tool window with asynchronous repository operations."""
import queue
import threading
import os
from pathlib import Path
from PySide6.QtCore import QTimer, Qt, QSize
from PySide6.QtGui import QFontDatabase, QFont, QIcon, QPixmap, QPainter, QPainterPath, QPen, QColor
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QLineEdit, QPushButton, QFileDialog, QMessageBox, QMainWindow,
                              QWidget, QToolBar, QSizePolicy, QSplitter, QFrame, QScrollArea, QStyle, QComboBox, QListView)
from .git import GitTool
from .git_installation import GitInstallation
from .git_commit_view import GitCommitView
from ..core.config import Config
from ..ui.launcher import Launcher
from ..ui.dialogs import Dialogs
from ..ui.button_gradients import ButtonGradients

class GitWindow:
    _window = None

    @classmethod
    def open(cls, parent=None):
        if cls._window is not None and cls._window.isVisible():
            cls._window.raise_()
            cls._window.activateWindow()
            cls.check_access_if_licensed(cls._window)
            GitCommitView.reload(cls._window)
            from .git_incoming_updates import GitIncomingUpdates
            GitIncomingUpdates.check(cls._window)
            return cls._window
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
        QApplication.instance().setFont(QFont("Segoe UI", 10))
        # An owned Windows tool window stays above its owner, preventing the
        # Launcher button from raising that owner. Keep tools independent.
        window = QMainWindow()
        cls._window = window
        window.setProperty("siLAssistentTool", True)
        window.setWindowFlag(Qt.WindowType.Window, True)
        window.setWindowTitle("siLAssistent - Git")
        window.setWindowIcon(Launcher.icon())
        window.setStyleSheet(Dialogs.style() + """
            QLineEdit {padding:6px; border:1px solid #334155; border-radius:3px; background:#0f172a;}
            QToolBar {background:#2a2a3e; spacing:6px; padding:5px; border-bottom:1px solid #334155;}
            QFrame#gitWorkspace {border:1px solid #334155;}
            QStatusBar {background:#2a2a3e; color:#94a3b8;}
            QComboBox {background:#0f172a; color:#e2e8f0; padding:6px; border:1px solid #475569; border-radius:3px; font:14pt 'Segoe UI';}
            QComboBox QAbstractItemView {background:#1e1e2e; color:#e2e8f0; selection-background-color:#bbf7d0; selection-color:#172554; font:14pt 'Segoe UI';}
            QComboBox QAbstractItemView::item {padding:6px;}
            QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected {background:#bbf7d0; color:#172554;}
        """)
        screen = QApplication.primaryScreen().availableGeometry()
        window.resize(min(1280, screen.width()-24), min(800, screen.height()-48))
        toolbar = QToolBar("Git", window)
        toolbar.setMovable(False)
        window.addToolBar(toolbar)
        toolbar.addWidget(QLabel("Git · M286-Setup"))
        request_access=QPushButton("Zugriff auf Setup-Repo beantragen")
        request_access.setObjectName("gitRequestAccess")
        ButtonGradients.apply(request_access,"#fed7aa")
        request_access.clicked.connect(lambda: cls.request_repo_access(window))
        toolbar.addWidget(request_access)
        request_license=QPushButton("Git User Lizenz beantragen")
        request_license.setObjectName("gitRequestLicense")
        ButtonGradients.apply(request_license,"#99f6e4")
        request_license.clicked.connect(lambda: cls.request_user_license(window))
        toolbar.addWidget(request_license)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        launcher = QPushButton("Launcher")
        launcher.setObjectName("gitLauncher")
        ButtonGradients.launcher(launcher)
        launcher.setToolTip("siLAssistent Launcher in den Vordergrund bringen")
        launcher.clicked.connect(cls.show_launcher)
        toolbar.addWidget(launcher)
        central = QWidget()
        window.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8,8,8,8)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter)
        sidebar = QScrollArea()
        sidebar.setWidgetResizable(True)
        sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sidebar.setMinimumWidth(250)
        sidebar.setFrameShape(QFrame.Shape.NoFrame)
        controls = QWidget()
        sidebar.setWidget(controls)
        layout = QVBoxLayout(controls)
        layout.setContentsMargins(4,4,8,4)
        layout.setSpacing(12)
        splitter.addWidget(sidebar)
        workspace = QFrame()
        workspace.setObjectName("gitWorkspace")
        GitCommitView.attach(window,workspace)
        splitter.addWidget(workspace)
        splitter.setStretchFactor(0,0)
        splitter.setStretchFactor(1,1)
        splitter.setSizes([340,940])
        window.statusBar().showMessage("Bereit")
        identity_row = QHBoxLayout()
        identity_row.addWidget(QLabel("User-ID"))
        status = QLabel("Zugriff wird geprüft ...")
        status.setObjectName("gitAccessStatus")
        status.setWordWrap(True)
        identity_row.addWidget(status, 1)
        layout.addLayout(identity_row)
        user = QLineEdit(GitTool.windows_user()["username"].upper())
        user.setObjectName("gitUserId")
        layout.addWidget(user)
        clone = QPushButton("Setup Lokal Download (Clonen)")
        clone.setObjectName("gitClone")
        ButtonGradients.apply(clone,"#86efac")
        layout.addWidget(clone)
        path_heading = QLabel("Lokaler Pfad zum SimFiles-Repository ::")
        path_heading.setStyleSheet("color:#f59e0b; font:12pt 'Segoe UI';")
        path_heading.setWordWrap(True)
        layout.addWidget(path_heading)
        path = QLineEdit(Config.state()["GitLocalRepoPath"])
        path.setObjectName("gitRepositoryPath")
        path.setPlaceholderText("Wird nach erfolgreichem Klonen eingetragen")
        browse = QPushButton()
        browse.setObjectName("gitBrowse")
        browse.setIcon(cls.folder_icon())
        browse.setIconSize(QSize(28,28))
        ButtonGradients.apply(browse,"#facc15",padding="6px")
        browse.setFixedWidth(48)
        browse.setAccessibleName("Ordner wählen")
        browse.setToolTip("Lokalen SimFiles-Ordner wählen")
        browse.clicked.connect(lambda: cls.choose_repository_folder(window))
        path.editingFinished.connect(lambda: cls.save_repository_path(window))
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_row.addWidget(path,1)
        path_row.addWidget(browse)
        layout.addLayout(path_row)
        layout.addSpacing(14)
        branch_heading=QLabel("Branch ::")
        branch_heading.setStyleSheet("color:#facc15; font:700 14pt 'Segoe UI';")
        layout.addWidget(branch_heading)
        branch_row=QHBoxLayout()
        branches=QComboBox()
        branches.setView(QListView())
        branches.view().setMouseTracking(True)
        branches.setObjectName("gitBranches")
        branches.setMinimumContentsLength(12)
        branches.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        branches.setPlaceholderText("Repo auswählen")
        activate=QPushButton("Aktivieren")
        activate.setObjectName("gitActivateBranch")
        ButtonGradients.apply(activate,"#99f6e4",font="700 12pt 'Segoe UI'")
        activate.setEnabled(False)
        branch_row.addWidget(branches,1)
        branch_row.addWidget(activate)
        layout.addLayout(branch_row)
        branch_note=QLabel("")
        branch_note.setWordWrap(True)
        branch_note.setMinimumWidth(0)
        branch_note.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        branch_note.setStyleSheet("font:14pt 'Segoe UI';")
        layout.addWidget(branch_note)
        layout.addSpacing(18)
        from .setup_updates import SetupUpdates
        pull=QPushButton("Pull (Update)")
        pull.setObjectName("gitPullUpdate")
        pull.setMinimumHeight(40)
        ButtonGradients.apply(pull,"#86efac",font="700 12pt 'Segoe UI'")
        pull.clicked.connect(lambda:SetupUpdates.manual(window,"pull"))
        layout.addWidget(pull)
        revert=QPushButton("Revert")
        revert.setObjectName("gitRevert")
        revert.setMinimumHeight(40)
        ButtonGradients.apply(revert,"#fed7aa",font="700 12pt 'Segoe UI'")
        revert.clicked.connect(lambda:SetupUpdates.manual(window,"revert"))
        layout.addWidget(revert)
        layout.addStretch()
        window._git = {"user":user, "clone":clone, "path":path,
                       "status":status, "branches":branches, "activate_branch":activate, "branch_note":branch_note,
                       "branch_queue":queue.Queue(), "branch_request":0, "queue":queue.Queue(), "busy":False, "allowed":False, "request":0}
        user.textChanged.connect(lambda: cls.identity_changed(window))
        clone.clicked.connect(lambda: cls.clone(window))
        activate.clicked.connect(lambda: cls.activate_branch(window))
        window.closeEvent = lambda event: cls.close_event(window,event)
        timer = QTimer(window)
        timer.timeout.connect(lambda: cls.poll(window))
        window._git["poll_timer"] = timer
        timer.start(100)
        window.showMaximized()
        if Config.state().get("GitInstallationState",False):
            cls.check_access_if_licensed(window)
        else:
            GitInstallation.start_probe(window,retry=lambda: cls.check_access_if_licensed(window))
        cls.load_branches(window)
        GitCommitView.reload(window)
        from .git_incoming_updates import GitIncomingUpdates
        GitIncomingUpdates.check(window)
        return window

    @classmethod
    def load_branches(cls, window):
        state=window._git
        if state["busy"]:
            return
        state["branch_request"]+=1
        state["branches"].clear()
        state["activate_branch"].setEnabled(False)
        path=Config.state()["GitLocalRepoPath"]
        if not path or not Path(path).is_dir():
            state["branch_note"].setText("Bitte einen lokalen SimFiles-Repo-Ordner wählen.")
            return
        state["branch_note"].setText("Branches werden geladen ...")
        state["branch_worker"]=threading.Thread(target=cls.branch_worker,args=(state["branch_queue"],state["branch_request"],path,None,None),daemon=True)
        state["branch_worker"].start()

    @classmethod
    def activate_branch(cls, window, approval=None):
        if not GitInstallation.require(window,retry=lambda: cls.activate_branch(window,approval=approval)):
            return
        from ..ui.git_licence import GitLicenceFlow
        state=window._git
        if state["busy"]:
            return
        if not GitLicenceFlow.allow_git_action(window):
            return
        # Confirmation owns its target; background metadata must never choose it again.
        branch=approval["target"] if approval is not None else state["branches"].currentText()
        if not branch:
            return
        state["busy"]=True
        state["request"]+=1
        state["branch_request"]+=1
        for name in ("user","clone","path","branches","activate_branch"):
            state[name].setEnabled(False)
        state["branch_note"].setText("Branch und Submodule werden aktiviert ...")
        window._commits["request"]+=1
        for label,listing in window._commits["panels"].values():
            label.setText("Branchwechsel läuft ...")
            listing.clear()
        cls.show_clone_progress(window,branch+" wird aktiviert", "branch_progress")
        path=Config.state()["GitLocalRepoPath"]
        state["branch_worker"]=threading.Thread(target=cls.branch_worker,args=(state["branch_queue"],state["branch_request"],path,branch,state["user"].text(),approval),daemon=True)
        state["branch_worker"].start()

    @classmethod
    def branch_worker(cls, messages, request, path, branch, user_id, approval=None):
        from .git_branches import GitBranches
        try:
            if branch:
                result=GitBranches.activate(path,branch,user_id,discard=approval) if approval is not None else GitBranches.activate(path,branch,user_id)
            else:result=GitBranches.list(path,refresh=False)
            messages.put((request,path,branch,result,None))
        except Exception as error:
            messages.put((request,path,branch,None,str(error)))

    @classmethod
    def poll_branches(cls, window):
        state=window._git
        try:
            request,path,branch,result,error=state["branch_queue"].get_nowait()
        except queue.Empty:
            return
        if request!=state["branch_request"] or path!=Config.state()["GitLocalRepoPath"]:
            return
        if branch:
            cls.finish_clone_progress(window,"branch_progress")
        if result and result.get("confirmation_required"):
            # A modal dialog processes timers too. Keep the operation reserved until
            # the decision returns, and do not launch a history reload in between.
            try:
                confirmed=Dialogs.confirm_branch_discard(result["active"],result["target"],result["approval"]["repositories"],window)
            finally:
                state["busy"]=False
                for name in ("user","clone","path","branches","activate_branch"):
                    state[name].setEnabled(True)
            if request!=state["branch_request"] or path!=Config.state()["GitLocalRepoPath"]:
                return
            if confirmed:
                cls.activate_branch(window,approval=result["approval"])
            else:
                GitCommitView.reload(window)
                import html
                state["branch_note"].setTextFormat(Qt.TextFormat.RichText)
                state["branch_note"].setText('Branchwechsel abgebrochen. Aktiver Branch: <span style="color:#40e0d0; font-weight:700;">'+html.escape(result["active"])+'</span>. Lokale Änderungen bleiben erhalten.')
            return
        if branch:
            state["busy"]=False
            GitCommitView.reload(window)
            for name in ("user","clone","path","branches"):
                state[name].setEnabled(True)
        if error:
            state["branch_note"].setTextFormat(Qt.TextFormat.PlainText)
            state["branch_note"].setText(error.replace("\\", "\\\u200b").replace("/", "/\u200b"))
            if branch:
                Dialogs.message("Branch konnte nicht vollständig aktiviert werden",error,window)
            state["activate_branch"].setEnabled(state["branches"].count()>0)
            return
        state["branches"].clear()
        state["branches"].addItems(result["branches"])
        index=state["branches"].findText(result["active"])
        state["branches"].setCurrentIndex(index if index>=0 else (0 if result["branches"] else -1))
        state["activate_branch"].setEnabled(bool(result["branches"]))
        import html
        active=html.escape(result["active"])
        note=('Aktiver Branch: <span style="color:#22c55e; font-weight:700;">'+active+"</span>" if active else "Kein lokaler Branch aktiv (Detached HEAD).")
        if result["warning"]:
            note=html.escape(result["warning"])+"<br>"+note
        state["branch_note"].setTextFormat(Qt.TextFormat.RichText)
        state["branch_note"].setText(note)
        if branch:
            from .git_incoming_updates import GitIncomingUpdates
            GitIncomingUpdates.check(window,restart=True)
            description="Aktuelle Branches der Submodule:"
            Dialogs.message(result["active"]+" Branch ist aktiviert.",description,window,
                            branch_status=result.get("submodule_branches",[]),target_branch=result["active"])

    @classmethod
    def request_user_license(cls, window):
        if not GitInstallation.require(window,retry=lambda: cls.request_user_license(window)):
            return
        from ..ui.git_licence import GitLicenceFlow
        if window._git["busy"]:
            return
        if GitLicenceFlow.question(window,"Wollen Sie eine Git User Lizenz beantragen?\n\n"+GitLicenceFlow.COST_WARNING):
            cls.start(window,"license_order")

    @classmethod
    def request_repo_access(cls, window):
        if not GitInstallation.require(window,retry=lambda: cls.request_repo_access(window)):
            return
        from .repo_request import RepoRequest
        RepoRequest.open(window)

    @classmethod
    def folder_icon(cls):
        pixmap = QPixmap(64,64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.moveTo(6,14)
        path.lineTo(25,14)
        path.lineTo(33,22)
        path.lineTo(58,22)
        path.lineTo(58,52)
        path.lineTo(6,52)
        path.closeSubpath()
        painter.setPen(QPen(QColor("#172554"),4))
        painter.drawPath(path)
        painter.end()
        return QIcon(pixmap)

    @classmethod
    def save_repository_path(cls, window, force_reload=False):
        value = window._git["path"].text().strip()
        previous=Config.state()["GitLocalRepoPath"]
        try:
            Config.set_state("GitLocalRepoPath", value)
        except (OSError, ValueError) as error:
            QMessageBox.warning(window,"Pfad konnte nicht gespeichert werden",str(error))
            return False
        if force_reload or value!=previous:
            cls.load_branches(window)
            GitCommitView.reload(window)
        return True

    @classmethod
    def choose_repository_folder(cls, window):
        if not GitInstallation.require(window,retry=lambda: cls.choose_repository_folder(window)):
            return
        if window._git["busy"]:
            return
        current = Config.state()["GitLocalRepoPath"]
        folder = QFileDialog.getExistingDirectory(window,"Lokalen SimFiles-Ordner wählen",current)
        if folder:
            window._git["path"].setText(folder)
            cls.save_repository_path(window)

    @classmethod
    def show_launcher(cls):
        window = Launcher._window
        if window is None:
            return
        window.showNormal()
        window.show()
        window.setWindowState((window.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        window.raise_()
        window.activateWindow()
        if os.name == "nt":
            from ..silEinrichten import SilverInstallation
            SilverInstallation.show_wizard(int(window.winId()))

    @classmethod
    def identity_changed(cls, window):
        state=window._git
        state["request"]+=1
        state.pop("license",None)
        state["allowed"]=False
        Config.set_state("GitUserState",False)
        state["status"].setText("Zugriff wird bei der nächsten Aktion geprüft.")
        state["status"].setStyleSheet("color:#94a3b8;")

    @classmethod
    def start(cls, window, operation, destination=None):
        state=window._git
        if state["busy"]:
            return
        state["request"]+=1
        request=state["request"]
        state["destination"]=destination
        user_id=state["user"].text()
        state["busy"]=operation in ("clone","license_login","license_order")
        if state["busy"]:
            state["user"].setEnabled(False)
            state["clone"].setEnabled(False)
        state["status"].setText("Zugriff wird geprüft ...")
        state["status"].setStyleSheet("color:#94a3b8;")
        if operation=="clone":
            cls.show_clone_progress(window)
        worker = threading.Thread(target=cls.worker, args=(state["queue"],operation,user_id,destination,request),daemon=True)
        state["worker"] = worker
        worker.start()

    @classmethod
    def show_clone_progress(cls, window, title="M286-Setup wird lokal auf Ziel Ordner geklont", key="clone_progress"):
        from ..silEinrichten import SilEinrichten
        dialog,body,animation=SilEinrichten.create_progress_card(title, "")
        body.hide()
        dialog.setParent(window,dialog.windowFlags())
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        for button in dialog.findChildren(QPushButton):
            button.hide()
        dialog.reject=lambda: None
        dialog.closeEvent=lambda event: event.ignore()
        window._git[key]=(dialog,animation)
        dialog.show()
        animation.start()
        SilEinrichten.foreground_dialog(dialog)

    @classmethod
    def finish_clone_progress(cls, window, key="clone_progress"):
        progress=window._git.pop(key,None)
        if progress:
            dialog,animation=progress
            animation.stop()
            dialog.accept()
            dialog.deleteLater()

    @classmethod
    def worker(cls, messages, operation, user_id, destination, request):
        try:
            if operation in ("license_login","license_order"):
                from .git_license import GitLicense
                from ..ui.git_licence import GitLicenceFlow
                notify=lambda notice:messages.put((request,user_id,"license_profile" if notice.get("license")=="profile_verification_required" else "license_checkout",notice,None))
                license_result=GitLicenceFlow.request_license(notify=notify) if operation=="license_order" else GitLicense.check(visible=True,notify=notify)
                result={"allowed":False,"status":"license_result",**license_result}
            else:
                result=GitTool.clone_repository(user_id,destination) if operation=="clone" else GitTool.repository_check(user_id,persist=False)
            messages.put((request,user_id,operation,result,None))
        except Exception as error:
            messages.put((request,user_id,operation,None,str(error)))

    @classmethod
    def poll(cls, window):
        if getattr(window,"_git_profile_notice_open",False) is True:return
        state=window._git
        cls.poll_branches(window)
        try:
            request,user_id,operation,result,error=state["queue"].get_nowait()
        except queue.Empty:
            return
        if request != state["request"] or user_id != state["user"].text():
            return
        if operation=="license_profile":
            from ..ui.git_licence import GitLicenceFlow
            GitLicenceFlow.profile_notice(window,result)
            return
        if operation=="license_checkout":
            from ..ui.git_licence import GitLicenceFlow
            GitLicenceFlow.checkout_notice(window)
            return
        state["busy"]=False
        if operation=="clone":
            cls.finish_clone_progress(window)
        state["user"].setEnabled(True)
        if operation in ("license_order","license_login"):
            if result and result.get("license")=="present":
                Config.set_state("GitUserLicenceState",True)
                window.statusBar().showMessage("Git User Lizenz vorhanden und gespeichert.")
                from ..ui.dialogs import Dialogs
                from .git_license import GitLicense
                try:
                    Dialogs.message("Git User Lizenz vorhanden","Sie besitzen bereits eine GitHub User Licence. Ein neuer Antrag ist nicht erforderlich.",window)
                finally:
                    GitLicense.close_confirmation_browser(result)
            else:
                detail=result.get("reason","Lizenz noch nicht bestätigt.") if result else error
                window.statusBar().showMessage(detail)
                from ..ui.dialogs import Dialogs
                window.showNormal();window.raise_();window.activateWindow()
                Dialogs.message("Git User Lizenz – Bestellung prüfen" if result and result.get("license")=="review" else "Git User Lizenz",detail,window)
            state["clone"].setEnabled(True)
            return
        state["allowed"]=bool(result and result["allowed"])
        Config.set_state("GitUserState",state["allowed"])
        state["clone"].setEnabled(True)
        if state["allowed"]:
            state["status"].setText("Zugriff auf das M286-Setup-Repo vorhanden")
            state["status"].setStyleSheet("color:#22c55e;")
        else:
            state["status"].setText("Zugriff für " + user_id + " nicht geprüft" if result and result["status"]=="identity_mismatch" else "Zugriff auf das M286-Setup-Repo nicht bestätigt")
            state["status"].setStyleSheet("color:#f59e0b;")
        if result and "license" in result:
            state["license"] = result["license"]
        if error:
            window.statusBar().showMessage("Klonen fehlgeschlagen." if operation=="clone" else error)
            if operation=="clone":
                from ..ui.dialogs import Dialogs
                Dialogs.message("M286-Setup konnte nicht geklont werden","Das Klonen konnte nicht abgeschlossen werden. Bitte prüfen Sie Netzwerk, Repo-/Submodul-Zugriff und Schreibrechte im Zielordner.\n\nEin unvollständiger Zielordner kann vorhanden sein; wählen Sie für einen erneuten Versuch einen neuen Zielordner.",window)
        elif result["status"] in ("git_error","unavailable") and operation!="check":
            from ..ui.dialogs import Dialogs
            Dialogs.message("Git-Vorgang nicht abgeschlossen",result.get("reason","Git erreicht den Server momentan nicht. Bitte Netzwerk, VPN und Git-Anmeldung prüfen."),window)
        elif result["status"] in ("authentication_required","authentication_or_access_required","unverified") and operation!="check":
            from .git_authentication import GitAuthentication
            destination=state.get("destination")
            incomplete=result.get("incomplete_path")
            GitAuthentication.offer(window,retry=lambda:cls.resume_after_authentication(window,operation,destination,incomplete))
        elif result["status"]=="git_missing":
            GitInstallation._resolved_executable=None
            GitInstallation.require(window)
        elif result["status"]=="cloned":
            state["path"].setText(result["path"])
            cls.save_repository_path(window,force_reload=True)
            window.statusBar().showMessage("Setup erfolgreich lokal geklont.")
            from ..ui.dialogs import Dialogs
            Dialogs.message("M286-Setup erfolgreich geklont","Repo wurde unter ::\n"+result["path"]+"\n\nerfolgreich geklont.",window)
        elif result["allowed"]:
            window.statusBar().showMessage("Zugriff bestätigt.")
            if operation=="preclone":
                folder=QFileDialog.getExistingDirectory(window,"Übergeordneten Ordner für SimFiles wählen",Config.state()["GitLocalRepoPath"])
                if folder:
                    cls.start(window,"clone",str(GitTool.clone_target(folder)))
        else:
            detail={"git_missing":"Git ist auf diesem Rechner nicht verfügbar.",
                    "identity_mismatch":"Die Rechte dieser User-ID wurden nicht abgefragt. Die vorhandene Git-Anmeldung gehört nicht automatisch zur eingegebenen ID. Bitte dieses Konto auf dessen Rechner oder mit eigener GitHub-Anmeldung prüfen.",
                    "unavailable":"Netzwerk oder Git-Dienst ist momentan nicht erreichbar.",
                    "unverified":"Zugriff nicht bestätigt. Eine fehlende Git-Anmeldung, Netzprobleme oder fehlende Rechte sind mögliche Ursachen."}.get(result["status"],result.get("reason",""))
            if result.get("license")=="present":
                detail += "\nGitHub-Enterprise-Lizenz vorhanden. Der Repo-Zugriff muss separat freigegeben sein."
            elif result.get("license")=="absent":
                detail += "\nKeine GitHub-Enterprise-Lizenz vorhanden."
            elif result.get("license")=="unknown":
                detail += "\nLizenzstatus nicht prüfbar. Bitte gegebenenfalls im Browser anmelden."
            state["status"].setToolTip(detail)
            window.statusBar().showMessage(detail)
            if operation != "check" and result.get("license")!="review":
                if result["status"] in ("access_denied","identity_mismatch"):
                    cls.access_notice(window,detail)
                else:
                    from ..ui.dialogs import Dialogs
                    Dialogs.message("Git-Zugriff noch nicht bestätigt",detail,window)

    @classmethod
    def resume_after_authentication(cls,window,operation,destination,incomplete=None):
        if incomplete:
            Dialogs.message("GitHub-Anmeldung bestätigt","Das zuvor begonnene Klonen hat einen unvollständigen Ordner hinterlassen:\n"+incomplete+"\n\nDer Ordner bleibt erhalten. Bitte starten Sie den Download (Clonen) erneut mit einem neuen Zielordner.",window)
        else:cls.start(window,"clone" if operation=="clone" else "preclone",destination if operation=="clone" else None)

    @classmethod
    def access_notice(cls, window, detail, force_request=False):
        box=QMessageBox(window)
        box.setWindowTitle("M286-Repo-Zugriff")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText('<span style="color:#f59e0b; font-size:12pt; font-weight:700;">Für diese Aktion benötigen Sie Zugriffsrechte auf das M286-Setup-Repo.</span>')
        box.setInformativeText(detail + "\nDie Berechtigung konnte nicht bestätigt werden.")
        actual_user = GitTool.windows_user()["username"].upper()
        different_user = not force_request and window._git["user"].text().strip().casefold() != actual_user.casefold()
        request=box.addButton("User-ID des aktuellen Users" if different_user else "Zugriff auf Setup-Repo beantragen",QMessageBox.ButtonRole.ActionRole)
        cancel=box.addButton("Abbrechen",QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        if not different_user:
            ButtonGradients.apply(request,"#fed7aa")
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True)
        box.exec()
        if different_user and box.clickedButton() is request:
            window._git["user"].setText(actual_user)
            cls.start(window,"check")
        elif not different_user and box.clickedButton() is request:
            cls.request_repo_access(window)

    @classmethod
    def clone(cls, window):
        if not GitInstallation.require(window,retry=lambda: cls.clone(window)):
            return
        state=window._git
        if state["busy"]:
            return
        from ..ui.git_licence import GitLicenceFlow
        if not GitLicenceFlow.allow_git_action(window):return
        cls.start(window,"preclone")

    @classmethod
    def check_access_if_licensed(cls,window):
        # Startup must not check repository access before a license is confirmed.
        if Config.state().get("GitUserLicenceState",False):cls.start(window,"check")
        else:window._git["status"].setText("Git User Lizenz vor dem Klonen bestätigen.")

    @classmethod
    def close_event(cls, window, event):
        if window._git["busy"]:
            window.statusBar().showMessage("Bitte den laufenden Git-Vorgang abwarten.")
            event.ignore()
        else:
            GitInstallation.cancel_probe(window)
            event.accept()
