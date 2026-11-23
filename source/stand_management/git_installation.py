"""Detect Git and launch the configured unattended installer on explicit request."""
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
            cls.missing_prompt(window, retry=state["retry"])

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
    def missing_prompt(cls, window, retry=None):
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
            cls.start(window,retry=retry)
        return False

    @classmethod
    def start(cls, window, retry=None):
        from .git_window import GitWindow
        if window._git["busy"]:
            return
        window._git["busy"]=True
        window._git["request"]+=1
        messages=queue.Queue()
        timer=QTimer(window)
        window._git_installation=(messages,timer)
        window._git_install_retry=retry
        timer.timeout.connect(lambda: cls.poll(window))
        timer.start(100)
        from ..ui.progress import ProgressWindow
        window._git_install_dialog=ProgressWindow.create("git",window)
        ProgressWindow.stage(window._git_install_dialog,"Git-Installation wird vorbereitet …",0)
        window._git_install_dialog.raise_();window._git_install_dialog.activateWindow()
        threading.Thread(target=cls.worker,args=(messages,),daemon=True).start()

    @classmethod
    def worker(cls, messages):
        try:
            cls.install(progress=lambda text,value:messages.put(("progress",text,value)))
            messages.put(None)
        except Exception as error:
            from ..core.network_share import NetworkShare
            messages.put(str(error) if NetworkShare.is_error(error) else "Git konnte nicht installiert oder erkannt werden. Bitte Netzwerkzugriff, Adminfreigabe und den Abschluss der Installation prüfen.")

    @classmethod
    def install(cls, progress=None):
        from ..core.network_share import NetworkShare
        installer=Path(Config.state()["GitInstallationPath"])
        NetworkShare.require_file(installer)
        if installer.suffix.lower()!=".exe" or not installer.is_file():
            raise RuntimeError("Git-Installer nicht verfügbar.")
        import tempfile
        import win32event,win32process,win32api
        from win32com.shell import shell,shellcon
        report=progress or (lambda text,value:None)
        with tempfile.TemporaryDirectory(prefix="silassistent-git-") as temporary:
            local=Path(temporary)/installer.name
            total=installer.stat().st_size;copied=0
            with local.open("wb") as outgoing:
                for block in NetworkShare.chunks(installer):
                    outgoing.write(block);copied+=len(block)
                    report("Git-Installer wird lokal vorbereitet …",int(copied*20/max(total,1)))
            parameters=cls.installer_arguments(Path(temporary)/"installation.log")
            report("Git wird still installiert. Eine Windows-Adminfreigabe kann erforderlich sein …",None)
            result=shell.ShellExecuteEx(fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,lpVerb="runas",lpFile=str(local),lpParameters=parameters,nShow=0)
            handle=result["hProcess"]
            try:
                last=None
                while win32event.WaitForSingleObject(handle,250)==win32event.WAIT_TIMEOUT:
                    current=cls.installer_progress(handle)
                    if current is not None and current!=last:
                        last=current;report("Git wird still installiert …",20+int(current*75))
                code=win32process.GetExitCodeProcess(handle)
            finally:
                win32api.CloseHandle(handle)
            if code not in (0,3010):
                raise RuntimeError("Git-Installation nicht erfolgreich abgeschlossen.")
        report("Git-Installation wird geprüft …",98)
        cls._resolved_executable=None
        executable=cls.executable()
        if not executable:
            raise RuntimeError("Git wurde nach der Installation nicht gefunden.")
        version=subprocess.run([executable,"--version"],capture_output=True,timeout=10,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if version.returncode:
            raise RuntimeError("Git ist nicht startbar.")
        Config.set_state("GitInstallationState",True)
        from .git_credential_manager import GitCredentialManager
        GitCredentialManager.clear()
        report("Git ist installiert und startbereit.",100)

    @classmethod
    def installer_arguments(cls,log):
        return subprocess.list2cmdline(["/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/NOCANCEL","/SP-",
            "/NORESTARTAPPLICATIONS", "/LOG="+str(log),
            "/COMPONENTS=gitlfs,assoc,assoc_sh,windowsterminal",
            "/o:EditorOption=Notepad", "/o:DefaultBranchOption=main", "/o:PathOption=Cmd",
            "/o:SSHOption=OpenSSH", "/o:CURLOption=WinSSL", "/o:CRLFOption=CRLFCommitAsIs",
            "/o:GitPullBehaviorOption=Merge", "/o:UseCredentialManager=Enabled",
            "/o:PerformanceTweaksFSCache=Enabled", "/o:EnableSymlinks=Disabled"])

    @classmethod
    def installer_progress(cls,handle):
        # Read Inno's real progress when Windows exposes the hidden progress bar.
        # Never manufacture percentages when elevation prevents access.
        try:
            import win32gui,win32process,psutil
            pid=win32process.GetProcessId(handle)
            pids={pid}|{process.pid for process in psutil.Process(pid).children(recursive=True)}
            import ctypes
            from ctypes import wintypes
            message=ctypes.WinDLL("user32",use_last_error=True).SendMessageTimeoutW
            message.argtypes=(wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM,wintypes.UINT,wintypes.UINT,ctypes.POINTER(ctypes.c_size_t))
            message.restype=wintypes.LPARAM
            def read(hwnd,command,parameter):
                result=ctypes.c_size_t()
                if not message(hwnd,command,parameter,0,3,100,ctypes.byref(result)):return None
                return result.value
            values=[]
            def child(hwnd,_):
                if "progress" not in win32gui.GetClassName(hwnd).casefold():return
                low=read(hwnd,0x407,1)
                high=read(hwnd,0x407,0)
                pos=read(hwnd,0x408,0)
                if low is not None and high is not None and pos is not None and high>low:values.append(max(0,min(1,(pos-low)/(high-low))))
            def window(hwnd,_):
                if win32process.GetWindowThreadProcessId(hwnd)[1] in pids:
                    win32gui.EnumChildWindows(hwnd,child,None)
            win32gui.EnumWindows(window,None)
            return max(values) if values else None
        except Exception:return None

    @classmethod
    def poll(cls, window):
        from .git_window import GitWindow
        from ..ui.dialogs import Dialogs
        from ..ui.progress import ProgressWindow
        messages,timer=window._git_installation
        while True:
            try:error=messages.get_nowait()
            except queue.Empty:return
            if isinstance(error,tuple) and error[0]=="progress":
                ProgressWindow.stage(window._git_install_dialog,error[1],error[2])
                continue
            break
        timer.stop()
        ProgressWindow.finish(getattr(window,"_git_install_dialog",None))
        window._git_install_dialog=None
        window._git["busy"]=False
        retry=getattr(window,"_git_install_retry",None);window._git_install_retry=None
        if error:
            Config.set_state("GitInstallationState",False)
            Dialogs.message("Git-Installation nicht abgeschlossen",error,window)
        elif retry:
            # Continue the original action once, after the installer and verification.
            QTimer.singleShot(0,retry)
        else:
            GitWindow.start(window,"check")
            GitWindow.load_branches(window)
