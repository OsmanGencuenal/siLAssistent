"""Detect Git and launch the configured interactive installer on explicit request."""
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
from ..core.config import Config

class GitInstallation:
    @classmethod
    def executable(cls):
        cached=getattr(cls,"_resolved_executable",None)
        if cached and Path(cached).is_file():return cached
        cls._resolved_executable=None
        from ..core.git_probe import GitProbe
        found=GitProbe.find_executable()
        if found:cls._resolved_executable=found
        return found

    @classmethod
    def require(cls, window, retry=None):
        if Config.state()["GitInstallationState"]:
            cached=getattr(cls,"_resolved_executable",None)
            if cached and Path(cached).is_file():return True
            cls._resolved_executable=None
        cls.start_probe(window,retry=retry,notify=True)
        return False

    @classmethod
    def start_probe(cls, window, retry=None, notify=False):
        from ..core.process_runtime import ProcessRuntime
        from ..core.git_probe import GitProbe
        import multiprocessing
        import time
        if getattr(window,"_git_probe",None):
            if notify:
                window._git_probe["retry"]=retry
                window._git_probe["notify"]=True
            return
        ProcessRuntime.configure()
        context=multiprocessing.get_context("spawn")
        receiver,sender=context.Pipe(duplex=False)
        process=context.Process(target=GitProbe.run,args=(sender,),daemon=True)
        timer=QTimer(window)
        state={"process":process,"receiver":receiver,"timer":timer,"started":time.monotonic(),"result":None,"retry":retry,"notify":notify}
        window._git_probe=state
        try:
            process.start()
        except Exception:
            receiver.close()
            sender.close()
            window._git_probe=None
            if notify:
                QMessageBox.warning(window,"Git-Prüfung","Die Hintergrundprüfung konnte nicht gestartet werden.")
            return
        sender.close()
        timer.timeout.connect(lambda: cls.poll_probe(window))
        timer.start(100)

    @classmethod
    def poll_probe(cls, window):
        import time
        state=window._git_probe
        process=state["process"]
        try:
            if state["result"] is None and state["receiver"].poll(0):
                state["result"]=state["receiver"].recv()
        except (OSError,EOFError):
            state["result"]={"path":None,"error":"Die Hintergrundprüfung wurde unerwartet beendet."}
        if process.is_alive():
            if time.monotonic()-state["started"]>30:
                state["result"]={"path":None,"error":"Die Git-Prüfung hat zu lange gedauert."}
                process.terminate()
            return
        process.join(timeout=0)
        process.close()
        state["receiver"].close()
        state["timer"].stop()
        window._git_probe=None
        if state.get("cancelled"):
            return
        result=state["result"] or {"error":"Kein Prüfergebnis erhalten."}
        if result.get("error"):
            if result.get("path"):Config.set_state("GitInstallationState",True)
            if state["notify"]:
                QMessageBox.warning(window,"Git-Prüfung",result["error"])
            return
        found=bool(result.get("path"))
        Config.set_state("GitInstallationState",found)
        if found:
            cls._resolved_executable=result["path"]
            if state["retry"]:
                state["retry"]()
        elif state["notify"]:
            cls.missing_prompt(window)

    @classmethod
    def cancel_probe(cls, window):
        state=getattr(window,"_git_probe",None)
        if state:
            state["cancelled"]=True
            state["retry"]=None
            state["notify"]=False
            if state["process"].is_alive():
                state["process"].terminate()
            cls.poll_probe(window)

    @classmethod
    def missing_prompt(cls, window):
        if window._git["busy"]:
            return
        box=QMessageBox(window)
        box.setWindowTitle("Git-Installation erforderlich")
        box.setText("Sie haben keine Git-Installation. Für die Verwendung des Tools ist sie erforderlich.")
        install=box.addButton("Git-Installieren",QMessageBox.ButtonRole.ActionRole)
        cancel=box.addButton("Abbrechen",QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is install:
            cls.start(window)
        return False

    @classmethod
    def start(cls, window):
        from .git_window import GitWindow
        if window._git["busy"]:
            return
        window._git["busy"]=True
        window._git["request"]+=1
        messages=queue.Queue()
        timer=QTimer(window)
        window._git_installation=(messages,timer)
        timer.timeout.connect(lambda: cls.poll(window))
        timer.start(100)
        GitWindow.show_clone_progress(window,"Git wird installiert","git_install_progress")
        threading.Thread(target=cls.worker,args=(messages,),daemon=True).start()

    @classmethod
    def worker(cls, messages):
        try:
            cls.install()
            messages.put(None)
        except Exception:
            messages.put("Git konnte nicht installiert oder erkannt werden. Bitte Netzwerkzugriff, Adminfreigabe und den Abschluss der Installation prüfen.")

    @classmethod
    def install(cls):
        installer=Path(Config.state()["GitInstallationPath"])
        if installer.suffix.lower()!=".exe" or not installer.is_file():
            raise RuntimeError("Git-Installer nicht verfügbar.")
        import win32event,win32process,win32api
        from win32com.shell import shell,shellcon
        result=shell.ShellExecuteEx(fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,lpVerb="runas",lpFile=str(installer),nShow=1)
        handle=result["hProcess"]
        try:
            win32event.WaitForSingleObject(handle,win32event.INFINITE)
            code=win32process.GetExitCodeProcess(handle)
        finally:
            win32api.CloseHandle(handle)
        if code not in (0,3010):
            raise RuntimeError("Git-Installation nicht erfolgreich abgeschlossen.")
        executable=cls.executable()
        if not executable:
            raise RuntimeError("Git wurde nach der Installation nicht gefunden.")
        version=subprocess.run([executable,"--version"],capture_output=True,timeout=10,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if version.returncode:
            raise RuntimeError("Git ist nicht startbar.")
        Config.set_state("GitInstallationState",True)

    @classmethod
    def poll(cls, window):
        from .git_window import GitWindow
        from ..ui.dialogs import Dialogs
        messages,timer=window._git_installation
        try:
            error=messages.get_nowait()
        except queue.Empty:
            return
        timer.stop()
        GitWindow.finish_clone_progress(window,"git_install_progress")
        window._git["busy"]=False
        if error:
            Config.set_state("GitInstallationState",False)
            Dialogs.message("Git-Installation nicht abgeschlossen",error,window)
        else:
            Dialogs.message("Git installiert","Git wurde erfolgreich installiert. Sie können die gewünschte Aktion jetzt erneut starten.",window)
            GitWindow.start(window,"check")
            GitWindow.load_branches(window)
