"""Handle Silver's module-editor Save dialog during an explicitly requested apply."""
from contextlib import contextmanager
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

    _local=threading.local()

    @classmethod
    def clear_editor(cls,pid):
        from .ui_client import SilverUiClient
        session=getattr(cls._local,"session",None)
        if session is None:
            with cls.during_apply(pid):return cls.clear_editor(pid)
        if session["pid"]!=pid:raise RuntimeError("UI-Automation gehört zu einem anderen Silver-Prozess.")
        # The persistent helper keeps saving modal dialogs while Select() in
        # this separate MTA helper may wait for the Silver UI to complete.
        editor=SilverUiClient.start(pid)
        try:return SilverUiClient.call(editor,"clear")
        finally:SilverUiClient.close(editor,grace=0)

    @classmethod
    def clear_on_desktop(cls,desktop,pid,native=None,pids=None):
        # Executed only by the isolated UIA worker, on its single MTA thread.
        import time
        import re
        windows=desktop.windows(process=pid,title_re=r"^Silver .*",visible_only=True)
        candidates=[]
        for window in windows:
            candidates.extend(item for item in window.descendants(control_type="TreeItem")
                              if re.fullmatch(r"GUI(?:\s+\(\d+\))?",item.window_text().strip()))
        if len(candidates)!=1:
            raise RuntimeError("Der GUI-Knoten des verbundenen Silver-Setups konnte nicht eindeutig gefunden werden. SFU-Änderungen wurden nicht gestartet.")
        gui=candidates[0];gui.select()
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if native is not None:
                cls.save_dialogs(native,pids or [pid],native=True)
                cls.save_dialogs(desktop,pids or [pid])
            dialogs=desktop.windows(process=pid,title="Module Changed",visible_only=True)
            if not dialogs and gui.is_selected():return True
            time.sleep(.1)
        raise RuntimeError("Silver hat den aktiven SFU-Editor nicht rechtzeitig abgeschlossen. Bitte die offene Save-Meldung prüfen.")

    @classmethod
    @contextmanager
    def during_apply(cls,pid):
        from .ui_client import SilverUiClient
        previous=getattr(cls._local,"session",None)
        if previous is not None:
            if previous["pid"]!=pid:raise RuntimeError("UI-Automation läuft bereits für einen anderen Silver-Prozess.")
            yield
            return
        session=SilverUiClient.start(pid)
        cls._local.session=session
        try:yield
        finally:
            cls._local.session=None
            SilverUiClient.close(session)
