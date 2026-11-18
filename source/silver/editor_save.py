"""Handle Silver's module-editor Save dialog during an explicitly requested apply."""
from contextlib import contextmanager
import logging
import threading

class SilverEditorSave:
    @classmethod
    def save_dialogs(cls,desktop,pids,native=False):
        count=0
        for pid in pids:
            for dialog in desktop.windows(process=pid,title="Module Changed",visible_only=True):
                candidates=dialog.descendants(class_name="Button") if native else dialog.descendants(control_type="Button")
                buttons=[button for button in candidates if button.window_text().replace("&","").strip()=="Save"]
                if len(buttons)==1 and buttons[0].is_enabled():
                    if native:buttons[0].click()
                    else:buttons[0].invoke()
                    count+=1
        return count

    @classmethod
    def clear_editor(cls,pid):
        """Leave the SFU editor before API writes can dirty a stale editor buffer."""
        if pid is None:raise RuntimeError("Silver-Prozess für die Editor-Bestätigung fehlt.")
        import pythoncom
        import time
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        try:
            from pywinauto import Desktop
            desktop=Desktop(backend="uia")
            windows=desktop.windows(process=pid,title_re=r"^Silver .*",visible_only=True)
            candidates=[]
            import re
            for window in windows:
                candidates.extend(item for item in window.descendants(control_type="TreeItem")
                                  if re.fullmatch(r"GUI(?:\s+\(\d+\))?",item.window_text().strip()))
            if len(candidates)!=1:
                raise RuntimeError("Der GUI-Knoten des verbundenen Silver-Setups konnte nicht eindeutig gefunden werden. SFU-Änderungen wurden nicht gestartet.")
            gui=candidates[0]
            gui.select()
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                dialogs=desktop.windows(process=pid,title="Module Changed",visible_only=True)
                if not dialogs and gui.is_selected():return
                time.sleep(0.1)
            raise RuntimeError("Silver hat den aktiven SFU-Editor nicht rechtzeitig abgeschlossen. Bitte die offene Save-Meldung prüfen.")
        finally:pythoncom.CoUninitialize()

    @classmethod
    def monitor(cls,pid,stop):
        # Initialise COM before importing pywinauto/comtypes in this thread.
        import pythoncom
        import psutil
        from ..core.runtime import Runtime
        log=logging.getLogger(__name__+".monitor")
        handler=logging.FileHandler(Runtime.data_root()/"silver_editor_save.log",encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler);log.setLevel(logging.INFO)
        initialized=False
        try:
            pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED);initialized=True
            from pywinauto import Desktop
            process=psutil.Process(pid);created=process.create_time()
            native=Desktop(backend="win32");uia=Desktop(backend="uia")
            log.info("Watching connected Silver pid=%s",pid)
            while not stop.is_set():
                if not process.is_running() or process.create_time()!=created:return
                pids=[process.pid]+[child.pid for child in process.children(recursive=True)]
                for desktop,is_native in ((native,True),(uia,False)):
                    try:
                        count=cls.save_dialogs(desktop,pids,native=is_native)
                        if count:log.info("Confirmed Save: backend=%s pids=%s count=%s","win32" if is_native else "uia",pids,count)
                    except Exception:log.exception("Save dialog handling failed: native=%s",is_native)
                stop.wait(0.2)
        except psutil.NoSuchProcess:log.info("Connected Silver process ended")
        except Exception:log.exception("Silver Save monitor could not run")
        finally:
            if initialized:pythoncom.CoUninitialize()
            log.removeHandler(handler);handler.close()

    @classmethod
    @contextmanager
    def during_apply(cls,pid):
        stop=threading.Event()
        monitor=None
        if pid is not None:
            monitor=threading.Thread(target=cls.monitor,args=(pid,stop),daemon=True)
            monitor.start()
        try:yield
        finally:
            # Silver can post the editor dialog after the initiating RPC returns.
            if monitor is not None:stop.wait(3)
            stop.set()
            if monitor is not None:monitor.join(timeout=2)
