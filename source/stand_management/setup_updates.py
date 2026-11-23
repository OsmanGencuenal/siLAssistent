"""Setup counter checks and updates in spawn workers, without blocking Qt."""
from ..core.network_share import NetworkShare
import configparser
import multiprocessing
import os
from pathlib import Path
import shutil
import time
import uuid
from ..core.config import Config
from ..core.errors import RepoAccessRequired,GitMissing
from ..core.process_runtime import ProcessRuntime


class SetupCancelled(RuntimeError):
    pass


class SetupUpdates:
    @classmethod
    def manifest(cls):
        parser=configparser.ConfigParser(interpolation=None)
        raw=NetworkShare.read_bytes(Config.load()["update_ini_path"])
        try: text=raw.decode("utf-8-sig")
        except UnicodeDecodeError: text=raw.decode("cp1252")
        parser.read_string(text)
        Config.initialize_setup_counter(parser)
        Config.sync_update_paths(parser)
        counter=parser.getint("UPDATE","silSetupVersionCounter")
        if counter<0: raise ValueError("Ungültiger Setup-Counter auf dem Laufwerk.")
        return {"counter":counter,"source":Config.network_path(parser.get("PATH","silSetupPath",fallback=parser.get("UPDATE","silSetupPath",fallback="")).strip())}

    @classmethod
    def check(cls):
        release=cls.manifest()
        local=int(Config.state()["silSetupVersionCounter"])
        return {**release,"available":local<release["counter"]}

    @classmethod
    def check_mode(cls,mode,user_id=None):
        # The shared update offer must also work without Git/license/repo access.
        # Check those only after the user chooses the Git route.
        return cls.check()

    @classmethod
    def git_update(cls, path, progress=None):
        from .git_actions import GitActions
        return GitActions.pull(path,progress=progress)

    @classmethod
    def check_cancelled(cls,cancelled):
        if cancelled is not None and cancelled.is_set():
            raise SetupCancelled("Aktion abgebrochen. Der bisherige Setup-Stand bleibt erhalten.")

    @classmethod
    def copy_file(cls,source,target,cancelled):
        cls.check_cancelled(cancelled)
        with open(target,"wb") as outgoing:
            for block in NetworkShare.chunks(source):
                cls.check_cancelled(cancelled)
                outgoing.write(block)
        shutil.copystat(source,target)
        return target

    @classmethod
    def copy_update(cls, source, target, cancelled=None):
        cls.check_cancelled(cancelled)
        with NetworkShare.access(source):source=Path(source).resolve()
        NetworkShare.require_directory(source)
        target=Path(target).resolve()
        if not source.is_dir() or source.name.casefold()!="simfiles":
            raise ValueError("Der LW-Quellpfad muss auf einen vorhandenen SimFiles-Ordner zeigen.")
        if target.name.casefold()!="simfiles" or source==target or source.is_relative_to(target) or target.is_relative_to(source):
            raise ValueError("Quell- und Zielordner sind nicht für dieses Setup-Update geeignet.")
        if (target/".git").exists():
            raise ValueError("Dieser Zielordner ist ein Git-Repo. Bitte über Git aktualisieren.")
        for base,dirs,files in os.walk(source,onerror=NetworkShare.walk_error):
            cls.check_cancelled(cancelled)
            for name in dirs+files:
                item=Path(base)/name
                if item.is_symlink() or (hasattr(os.path,"isjunction") and os.path.isjunction(item)):
                    raise ValueError("Verknüpfungen im LW-Setup werden nicht automatisch kopiert.")
        target.parent.mkdir(parents=True,exist_ok=True)
        stage=target.parent/(".silassistent-stage-"+uuid.uuid4().hex)
        backup=target.parent/("SimFiles-backup-"+uuid.uuid4().hex)
        try:
            shutil.copytree(source,stage,ignore=shutil.ignore_patterns(".git"),
                            copy_function=lambda source,destination:cls.copy_file(source,destination,cancelled))
            cls.check_cancelled(cancelled)
            # The following short rename/rollback sequence must finish atomically.
            if target.exists(): target.rename(backup)
            try: stage.rename(target)
            except Exception:
                if backup.exists() and not target.exists(): backup.rename(target)
                raise
        finally:
            if stage.exists() and stage.parent==target.parent and stage.name.startswith(".silassistent-stage-"):
                shutil.rmtree(stage)
        return "Setup wurde unter ::\n\n"+str(target)+"\n\nkopiert"+("\n\nVorheriger Stand gesichert unter ::\n"+str(backup) if backup.exists() else "")

    @classmethod
    def worker(cls, pipe, operation, release=None, target=None, cancelled=None, mode=None, user_id=None):
        try:
            if release is not None:release={"counter":release["counter"],"source":release["source"]}
            if operation in ("pull","revert"):
                from .git_actions import GitActions
                if release is not None and cls.manifest()!=release:
                    raise RuntimeError("Der LW-Setupstand hat sich geändert. Bitte erneut prüfen.")
                result=GitActions.pull(target,progress=lambda branch:pipe.send({"progress_branch":branch})) if operation=="pull" else GitActions.revert(target)
                if release is not None:
                    if cls.manifest()!=release:
                        raise RuntimeError("LW-Setupstand hat sich während des Updates geändert. Bitte erneut prüfen; Counter bleibt unverändert.")
                    Config.set_state("silSetupVersionCounter",str(release["counter"]))
            elif operation=="check": result=cls.check_mode(mode,user_id)
            else:
                current=cls.manifest()
                if operation=="configure_drive":release=current
                if current!=release: raise RuntimeError("Der LW-Setupstand hat sich geändert. Bitte erneut prüfen.")
                result=cls.git_update(target,progress=lambda branch:pipe.send({"progress_branch":branch})) if operation=="git" else cls.copy_update(release["source"],target,cancelled=cancelled)
                if cls.manifest()!=release: raise RuntimeError("LW-Setupstand hat sich während des Updates geändert. Bitte erneut prüfen; Counter bleibt unverändert.")
                if operation in ("configure_drive","drive"):Config.set_state("DriveSetupLocalPath",str(target))
                Config.set_state("silSetupVersionCounter",str(release["counter"]))
            pipe.send({"result":result,"error":None})
        except GitMissing as error:
            pipe.send({"result":None,"error":str(error),"git_missing":True})
        except RepoAccessRequired as error:
            pipe.send({"result":None,"error":str(error),"repo_access_required":True})
        except SetupCancelled as error:
            pipe.send({"result":str(error),"error":None,"cancelled":True})
        except Exception as error:
            pipe.send({"result":None,"error":str(error)})
        finally: pipe.close()

    @classmethod
    def manual(cls,parent,operation,release=None):
        from .git_installation import GitInstallation
        from .git import GitTool
        from ..ui.dialogs import Dialogs
        from ..ui.git_licence import GitLicenceFlow
        if getattr(cls,"_active",False) or parent._git["busy"]:return
        if not GitInstallation.require(parent,retry=lambda:cls.manual(parent,operation,release=release)):return
        if not GitLicenceFlow.allow_git_action(parent):return
        if parent._git["user"].text().strip().casefold()!=GitTool.windows_user()["username"].casefold():
            Dialogs.message("User-ID nicht bestätigt","Bitte die User-ID des angemeldeten Windows-Benutzers verwenden.",parent);return
        if operation=="revert":
            from PySide6.QtWidgets import QMessageBox
            answer=QMessageBox.question(parent,"Versionierte Änderungen verwerfen?","Alle Änderungen an versionierten Dateien in SimFiles und seinen Submodulen werden auf den jeweiligen lokalen Commit-Stand zurückgesetzt. Diese Änderungen werden verworfen. Fortfahren?")
            if answer!=QMessageBox.StandardButton.Yes:return
        if release is not None:
            # Discard a startup access-check reply that could unlock this new pull.
            parent._git["request"]=parent._git.get("request",0)+1
        cls._active=True;parent._git["busy"]=True
        cls.spawn(parent,"git",operation,release=release,target=Config.state()["GitLocalRepoPath"])

    @classmethod
    def watch(cls,parent,mode):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        cls._hourly_context=(parent,mode)
        if getattr(cls,"_hourly_timer",None) is None:
            cls._hourly_timer=QTimer(QApplication.instance())
            cls._hourly_timer.timeout.connect(cls.hourly_tick)
        cls.hourly_tick(offer=True)

    @classmethod
    def hourly_tick(cls,now=None,offer=False):
        from datetime import datetime
        now=now or datetime.now().astimezone()
        # Wake at the next full hour. Busy operations are retried after 15 seconds.
        timer=getattr(cls,"_hourly_timer",None)
        if timer is not None:
            timer.setSingleShot(True)
            timer.start(max(1,int((3600-now.minute*60-now.second-now.microsecond/1000000)*1000)))
        context=getattr(cls,"_hourly_context",None)
        if not context:return
        parent,mode=context
        from ..ui.launcher import Launcher
        from shiboken6 import isValid
        if not isValid(parent) or not parent.isVisible():parent=Launcher._window
        if parent is None or not isValid(parent):return
        if getattr(cls,"_active",False) or getattr(cls,"_update_dialog_open",False) or getattr(parent,"_git",{}).get("busy",False):
            if timer is not None:timer.start(15000)
            return
        stamp=now.strftime("%Y-%m-%d %H %z")
        checked=getattr(cls,"_hourly_checked",{})
        if checked.get(mode)==stamp and not offer:return
        checked[mode]=stamp
        cls._hourly_checked=checked
        cls._automatic_check=True
        cls.start(parent,mode,offer=True)

    @classmethod
    def start(cls, parent, mode, offer=True):
        if getattr(cls,"_active",False): return
        cls._active=True
        cls.spawn(parent,mode,"check",offer=offer)

    @classmethod
    def spawn(cls,parent,mode,operation,release=None,target=None,offer=True):
        from PySide6.QtCore import QTimer
        ProcessRuntime.configure()
        context=multiprocessing.get_context("spawn")
        receiver,sender=context.Pipe(False)
        cancelled=context.Event()
        user_id=parent._git["user"].text() if mode=="git" and hasattr(parent,"_git") else None
        process=context.Process(target=cls.worker,args=(sender,operation,release,target,cancelled,mode,user_id),daemon=True)
        timer=QTimer(parent)
        state={"process":process,"receiver":receiver,"timer":timer,"parent":parent,"mode":mode,"operation":operation,"result":None,"started":time.monotonic(),"cancelled":cancelled}
        state["automatic"]=bool(getattr(cls,"_automatic_check",False)) if operation=="check" else False
        cls._automatic_check=False
        state["offer"]=offer
        cls._state=state
        try: process.start()
        except Exception as error:
            receiver.close();sender.close();process.close();cls._active=False
            if hasattr(parent,"_git"):parent._git["busy"]=False
            from ..ui.dialogs import Dialogs
            Dialogs.message("Git-/Setup-Vorgang nicht gestartet",str(error),parent)
            return
        sender.close()
        timer.timeout.connect(lambda:cls.poll(state))
        timer.start(150)
        if operation!="check":
            from ..silEinrichten import SilEinrichten
            copying=operation in ("drive","configure_drive")
            title="M286-Setup wird kopiert nach ::" if copying else ("Versionierte Änderungen werden zurückgesetzt" if operation=="revert" else "M286-Setup wird aktualisiert")
            dialog,body,animation=SilEinrichten.create_progress_card(title,str(target) if copying else "")
            if copying:
                body.setStyleSheet("color:#f59e0b; font:14pt 'Segoe UI';")
            from PySide6.QtCore import Qt
            dialog.setParent(parent,dialog.windowFlags())
            dialog.setWindowModality(Qt.WindowModality.WindowModal)
            state["progress"]=(dialog,animation)
            from PySide6.QtWidgets import QPushButton,QDialog
            cancel=next(button for button in dialog.findChildren(QPushButton) if button.text()=="Abbrechen")
            cancel.clicked.disconnect()
            state["cancel_button"]=cancel
            if copying:
                cancel.clicked.connect(lambda:cls.cancel(state))
                dialog.closeEvent=lambda event:(cls.cancel(state),event.ignore())
                dialog.keyPressEvent=lambda event:cls.cancel(state) if event.key()==Qt.Key.Key_Escape else QDialog.keyPressEvent(dialog,event)
            else:
                cancel.hide()
                dialog.closeEvent=lambda event:event.ignore()
                dialog.keyPressEvent=lambda event:event.ignore() if event.key()==Qt.Key.Key_Escape else QDialog.keyPressEvent(dialog,event)
            dialog.show();animation.start()
            SilEinrichten.foreground_dialog(dialog)
            QTimer.singleShot(0,lambda:SilEinrichten.foreground_dialog(dialog))

    @classmethod
    def cancel(cls,state):
        if state["operation"] not in ("drive","configure_drive"):return
        state["cancelled"].set()
        button=state.get("cancel_button")
        if button is not None:
            button.setText("Wird abgebrochen ...")
            button.setEnabled(False)

    @classmethod
    def show_pull_branch(cls,state,branch):
        import html
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel
        if not branch or not state.get("progress"):return
        dialog,animation=state["progress"]
        heading=dialog.findChild(QLabel,"heading")
        heading.setTextFormat(Qt.TextFormat.RichText)
        heading.setText('M286-Setup wird aus <span style="color:#f59e0b;">'+html.escape(branch)+'</span> aktualisiert')
        dialog.setWindowTitle("siLAssistent - M286-Setup wird aus "+branch+" aktualisiert")

    @classmethod
    def poll(cls,state):
        from ..ui.dialogs import Dialogs
        process=state["process"]
        try:
            if state["receiver"].poll(0):
                payload=state["receiver"].recv()
                if "progress_branch" in payload:
                    cls.show_pull_branch(state,payload["progress_branch"])
                    return
                state["result"]=payload
        except (EOFError,OSError): pass
        if process.is_alive(): return
        process.join(0);process.close();state["receiver"].close();state["timer"].stop()
        if state.get("progress"):
            dialog,animation=state["progress"];animation.stop();dialog.accept()
        cls._active=False
        if state["operation"]!="check" and hasattr(state["parent"],"_git"):
            state["parent"]._git["busy"]=False
            from .git_commit_view import GitCommitView
            GitCommitView.reload(state["parent"])
        result=state["result"] or {"error":"Die Setup-Hintergrundprüfung wurde unerwartet beendet."}
        if result.get("cancelled"):
            Dialogs.message("Aktion abgebrochen",result["result"],state["parent"]);return
        if result.get("git_missing"):
            from .git_installation import GitInstallation
            GitInstallation._resolved_executable=None
            GitInstallation.require(state["parent"])
            return
        if result.get("repo_access_required"):
            from .git_window import GitWindow
            GitWindow.access_notice(state["parent"],result["error"],force_request=True)
            return
        if result.get("error"):
            if state.get("automatic") and not NetworkShare.is_error(result["error"]):
                import logging
                logging.getLogger("siLAssistent").info("Automatische Setup-Prüfung: %s",result["error"])
                return
            Dialogs.message("Setup-Update nicht abgeschlossen",result["error"],state["parent"]);return
        if state["operation"]!="check":
            from .git_window import GitWindow
            if hasattr(state["parent"],"_git"):GitWindow.load_branches(state["parent"])
            Dialogs.message("Setup erfolgreich kopiert" if state["operation"] in ("drive","configure_drive") else ("Änderungen zurückgesetzt" if state["operation"]=="revert" else "Setup aktualisiert"),result["result"],state["parent"]);return
        release=result["result"]
        if not state.get("offer",True):return
        if not release["available"]: return
        cls.confirm(state["parent"],state["mode"],release)

    @classmethod
    def confirm(cls,parent,mode,release):
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtCore import QTimer
        from ..ui.dialogs import Dialogs
        from ..ui.button_gradients import ButtonGradients
        if getattr(cls,"_update_dialog_open",False):return
        cls._update_dialog_open=True
        try:
            dialog,footer,body=Dialogs.card("Setup-Update vorhanden","Ein neuer Setup-Stand ist verfügbar.\n\nWie möchten Sie Ihr lokales Setup aktualisieren?",parent)
            git=QPushButton("Update für Git-User");drive=QPushButton("Update für manuelle User");cancel=QPushButton("Abbrechen")
            ButtonGradients.apply(git,"#99f6e4",padding="10px 16px")
            ButtonGradients.apply(drive,"#172554",padding="10px 16px")
            git.clicked.connect(lambda:dialog.done(1));drive.clicked.connect(lambda:dialog.done(2));cancel.clicked.connect(dialog.reject)
            footer.addWidget(git);footer.addWidget(drive);footer.addWidget(cancel)
            QTimer.singleShot(0,lambda:Dialogs.foreground(dialog))
            choice=dialog.exec()
            if choice in (1,2):cls.update_selected(parent,"git" if choice==1 else "drive",release)
            else:
                from .git_commit_view import GitCommitView
                GitCommitView.preview_updates(parent)
        finally:cls._update_dialog_open=False

    @classmethod
    def update_selected(cls,parent,mode,release):
        from ..ui.dialogs import Dialogs
        if getattr(cls,"_active",False) or getattr(parent,"_git",{}).get("busy",False):
            Dialogs.message("Setup-Vorgang läuft","Bitte den laufenden Vorgang zuerst beenden.",parent);return
        key="GitLocalRepoPath" if mode=="git" else "DriveSetupLocalPath"
        target=Config.state()[key].strip()
        folder=Path(target) if target else None
        ready=folder is not None and folder.is_dir() and folder.name.casefold()=="simfiles"
        if ready and mode=="git":ready=(folder/".git").exists()
        if not ready:
            cls.setup_required(parent,mode)
            return
        snapshot={"counter":release["counter"],"source":release["source"]}
        if mode=="git":
            from .git import GitTool
            window=parent if hasattr(parent,"_git") else GitTool.open(parent)
            # Same entry point and safeguards as the existing Pull (Update) button.
            cls.manual(window,"pull",release=snapshot)
        else:
            if not snapshot["source"]:
                Dialogs.message("LW-Setup nicht konfiguriert","In der LW-Update-INI fehlt silSetupPath (Pfad zum SimFiles-Ordner).",parent);return
            cls._active=True
            if hasattr(parent,"_git"):parent._git["busy"]=True
            cls.spawn(parent,"drive","drive",release=snapshot,target=target)

    @classmethod
    def setup_required(cls,parent,mode):
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtCore import QTimer
        from ..ui.dialogs import Dialogs
        from ..ui.button_gradients import ButtonGradients
        git=mode=="git"
        text=("Bitte richten Sie das Git-Setup zuerst lokal ein. Es ist noch kein gültiger lokaler SimFiles-Repo-Ordner eingerichtet." if git else
              "Bitte richten Sie zuerst eine lokale manuelle Setup-Kopie ein. Es ist noch kein gültiger lokaler SimFiles-Ordner eingerichtet.")
        dialog,footer,body=Dialogs.card("Lokales Setup fehlt",text,parent)
        setup=QPushButton("Setup Lokal Download (Clonen)" if git else "Setup vom Laufwerk");cancel=QPushButton("Abbrechen")
        ButtonGradients.apply(setup,"#99f6e4" if git else "#172554",padding="10px 16px")
        setup.clicked.connect(dialog.accept);cancel.clicked.connect(dialog.reject)
        footer.addWidget(setup);footer.addWidget(cancel)
        QTimer.singleShot(0,lambda:Dialogs.foreground(dialog))
        if not dialog.exec():return
        if git:
            from .git import GitTool
            from .git_window import GitWindow
            window=parent if hasattr(parent,"_git") else GitTool.open(parent)
            GitWindow.clone(window)
        else:
            from .drive_setup import DriveSetup
            DriveSetup.open(parent)
