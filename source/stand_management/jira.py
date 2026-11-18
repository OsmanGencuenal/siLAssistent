"""Jira board selector and read-only access checks in a dedicated browser session."""
import queue
import threading
import time
from .jira_access import JiraAccess
from ..core.config import Config

class JiraTool:
    _commands=queue.Queue()
    _results=queue.Queue()
    _stopping=threading.Event()
    REQUEST_ACCESS="Jira-Zugriff beantragen"
    ACCESS_WAIT_SECONDS=30
    ACCESS_PENDING=("joining","site_access_pending")
    STATUS={"role_preparing":"ALICE-Rollensuche nach devottosil wird vorbereitet ...",
            "role_login_required":"Bitte direkt in Edge bei ALICE anmelden. Danach wird die Rollensuche automatisch vorbereitet.",
            "role_ready":"Die drei DEVOTTOSIL-Jira-Rollen werden angezeigt. Bitte selbst eine Rolle auswählen und mit Weiter fortfahren.",
            "role_timeout":"ALICE-Rollensuche konnte nicht bestätigt werden. Bitte Anmeldung und Verbindung prüfen oder in ALICE selbst nach devottosil suchen.",
            "role_error":"ALICE konnte nicht automatisch vorbereitet werden. Bitte Browser, Anmeldung und Netzwerk prüfen.",
            "login_required":"Bitte im geöffneten Edge-Fenster anmelden. Die Anmeldung ist noch kein Nachweis fehlender Rechte.",
            "site_access_pending":"Jira-Zugang noch nicht bestätigt. Atlassian zeigt den Zugangs-/Beitrittsprozess für die Firmen-Jira-Seite. Das gewählte Board wurde noch nicht geöffnet.",
            "joining":"Jira-Beitritt/Wartezustand erkannt. Das Board ist noch nicht geöffnet; fehlende Rechte sind damit nicht bewiesen.",
            "access_unconfirmed":"Jira-Zugang konnte nicht bestätigt werden. Sie befinden sich noch im Jira-Beitrittsprozess. Möglicherweise fehlt die Freigabe für die Firmen-Jira-Seite.",
            "allowed":"Zugriff auf dieses Jira-Board bestätigt.",
            "denied":"Jira verweigert den Zugriff auf dieses Board (angemeldete Sitzung, HTTP 403).",
            "not_visible_or_missing":"Das Board ist nicht sichtbar oder nicht vorhanden (HTTP 404). Fehlende Rechte und ein gelöschtes Board sind nicht sicher unterscheidbar.",
            "rate_limited":"Jira begrenzt die Abfragen. Bitte später erneut versuchen.",
            "service_error":"Jira meldet einen Serverfehler. Die Berechtigung konnte nicht geprüft werden.",
            "unknown":"Zugriff noch nicht eindeutig bestätigt. Bitte Anmeldung und Jira-Seite prüfen.",
            "timeout":"Das Board konnte innerhalb der Prüfzeit nicht bestätigt werden. Anmeldung, Wartezustand oder technische Störung prüfen; keine gesicherte Aussage zu fehlenden Rechten.",
            "error":"Jira konnte nicht geprüft werden. Bitte Edge, Netzwerk/VPN und die Anmeldung prüfen."}

    @classmethod
    def open(cls,parent=None):
        from PySide6.QtWidgets import QPushButton,QLabel
        from PySide6.QtCore import QTimer
        from ..ui.dialogs import Dialogs
        dialog,footer,body=Dialogs.card("Jira","Jira-Bereich auswählen. Eine erforderliche Anmeldung erfolgt direkt in Edge.",parent)
        dialog.setProperty("siLAssistentTool",True)
        colors={
            "Allgemein":("#bfdbfe","#dbeafe","#93c5fd"),
            "Testing-Grundmotor":("#bbf7d0","#dcfce7","#86efac"),
            "Testing-OBD":("#ddd6fe","#ede9fe","#c4b5fd"),
            "Testing-Sensorik":("#99f6e4","#ccfbf1","#5eead4"),
            "Jira-Zugriff beantragen":("#172554","#1e3a8a","#1e40af"),
        }
        for name in (*JiraAccess.BOARD_IDS,"Jira-Zugriff beantragen"):
            button=QPushButton(name)
            normal,hover,pressed=colors[name]
            foreground="#ffffff" if name==cls.REQUEST_ACCESS else "#172554"
            button.setStyleSheet("QPushButton {background:"+normal+"; color:"+foreground+"; font-weight:700; border:1px solid "+normal+";} QPushButton:hover {background:"+hover+";} QPushButton:pressed {background:"+pressed+";}")
            button.clicked.connect(lambda checked=False,name=name:cls.request_access(dialog) if name=="Jira-Zugriff beantragen" else cls.navigate(name))
            footer.addWidget(button)
        status=QLabel("");status.setWordWrap(True);footer.addWidget(status)
        dialog.resize(600,min(650,dialog.maximumHeight()))
        timer=QTimer(dialog);timer.timeout.connect(lambda:cls.poll(dialog,status));timer.start(200)
        dialog.exec();timer.stop()

    @classmethod
    def navigate(cls,name):
        cls.submit(name,navigate=True)

    @classmethod
    def retry(cls,name):
        # Keep the current session/page; never discard an in-progress login by reloading.
        cls.submit(name,navigate=False)

    @classmethod
    def submit(cls,name,navigate=True):
        if name not in JiraAccess.BOARD_IDS and name!=cls.REQUEST_ACCESS:raise ValueError("Unbekanntes Jira-Board.")
        cls._active_name=name
        if not getattr(cls,"_thread",None) or not cls._thread.is_alive():
            cls._stopping.clear()
            cls._thread=threading.Thread(target=cls.worker,daemon=True)
            cls._thread.start()
        cls._commands.put((name,navigate))
        cls._results.put((name,"role_preparing" if name==cls.REQUEST_ACCESS else "unknown"))

    @classmethod
    def check_board(cls,driver,name):
        last=None;pending_since=None;deadline=time.monotonic()+600
        while not cls._stopping.is_set() and time.monotonic()<deadline:
            if not cls._commands.empty():return
            state=JiraAccess.snapshot(driver,JiraAccess.BOARD_IDS[name])
            now=time.monotonic()
            if state in cls.ACCESS_PENDING:
                if pending_since is None:pending_since=now
                if now-pending_since>=cls.ACCESS_WAIT_SECONDS:
                    cls._results.put((name,"access_unconfirmed"))
                    return
            else:pending_since=None
            if state!=last:cls._results.put((name,state));last=state
            if state in ("allowed","denied","not_visible_or_missing","rate_limited","service_error"):
                if state in ("allowed","denied"):Config.set_state("JiraUserState",state=="allowed")
                return
            cls._stopping.wait(5)
        if not cls._stopping.is_set():cls._results.put((name,"timeout"))

    @classmethod
    def close_browser(cls,driver):
        if driver is not None:
            try:driver.quit()
            except Exception:pass

    @classmethod
    def ensure_browser(cls,driver):
        from selenium.common.exceptions import NoSuchWindowException
        if driver is not None:
            try:
                handles=driver.window_handles
                if handles:
                    try:current=driver.current_window_handle
                    except NoSuchWindowException:current=None
                    if current not in handles:driver.switch_to.window(handles[0])
                    return driver,False
            except Exception:
                pass
            cls.close_browser(driver)
        return JiraAccess.browser(),True

    @classmethod
    def session_lost(cls,error):
        from selenium.common.exceptions import InvalidSessionIdException,NoSuchWindowException
        if isinstance(error,(InvalidSessionIdException,NoSuchWindowException)):return True
        message=str(error).casefold()
        return any(marker in message for marker in ("invalid session id","no such window","disconnected","chrome not reachable","not connected to devtools","target window already closed","connection refused","10061"))

    @classmethod
    def worker(cls):
        from selenium.common.exceptions import TimeoutException
        driver=None
        try:
            while not cls._stopping.is_set():
                try:name,navigate=cls._commands.get(timeout=0.3)
                except queue.Empty:continue
                for attempt in range(2):
                    try:
                        driver,recreated=cls.ensure_browser(driver)
                        if recreated:navigate=True
                        if name==cls.REQUEST_ACCESS:
                            from .jira_alice import JiraAlice
                            JiraAlice.prepare(driver,cls._stopping,lambda state:cls._results.put((name,state)),interrupted=lambda:not cls._commands.empty())
                        else:
                            if navigate:
                                try:driver.get(JiraAccess.url(name))
                                except TimeoutException:
                                    # Only loading timeouts are handled by subsequent inspection.
                                    pass
                            cls.check_board(driver,name)
                        break
                    except Exception as error:
                        cls.close_browser(driver)
                        driver=None
                        if attempt==0 and cls.session_lost(error) and not cls._stopping.is_set():
                            navigate=True
                            continue
                        cls._results.put((name,"role_error" if name==cls.REQUEST_ACCESS else "error"))
                        break
        finally:
            cls.close_browser(driver)

    @classmethod
    def poll(cls,dialog,label):
        from ..ui.dialogs import Dialogs
        if getattr(dialog,"_jira_notice_open",False):return
        try:
            while True:
                name,state=cls._results.get_nowait()
                if name!=getattr(cls,"_active_name",name):continue
                label.setText(name+" ::\n"+cls.STATUS[state])
                label.setStyleSheet("color:"+("#22c55e" if state=="allowed" else "#fca5a5" if state=="denied" else "#f59e0b")+";")
                if state=="access_unconfirmed":
                    dialog._jira_notice_open=True
                    try:cls.pending_dialog(dialog,name)
                    finally:dialog._jira_notice_open=False
                if state in ("denied","not_visible_or_missing"):
                    Dialogs.message("Jira-Zugriff nicht möglich",cls.STATUS[state],dialog)
        except queue.Empty:pass

    @classmethod
    def pending_dialog(cls,parent,name):
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtCore import QTimer
        from ..ui.dialogs import Dialogs
        dialog,footer,body=Dialogs.card("Jira-Zugang konnte nicht bestätigt werden",name+"\n\nSie befinden sich noch im Jira-Beitrittsprozess. Möglicherweise fehlt die Freigabe für die Firmen-Jira-Seite.",parent)
        body.setStyleSheet("color:#f59e0b; font:12pt 'Segoe UI';")
        retry=QPushButton("Erneut prüfen")
        request=QPushButton("Jira-Zugriff beantragen")
        request.setStyleSheet("QPushButton {background:#172554; color:#ffffff; font-weight:700; border:1px solid #172554;} QPushButton:hover {background:#1e3a8a;} QPushButton:pressed {background:#1e40af;}")
        cancel=QPushButton("Abbrechen")
        retry.clicked.connect(dialog.accept)
        request.clicked.connect(lambda:dialog.done(2))
        cancel.clicked.connect(dialog.reject)
        footer.addWidget(retry);footer.addWidget(request);footer.addWidget(cancel)
        dialog.resize(600,min(520,dialog.maximumHeight()))
        QTimer.singleShot(0,lambda:Dialogs.foreground(dialog))
        result=dialog.exec()
        if result==1:cls.retry(name)
        elif result==2:cls.request_access(parent)

    @classmethod
    def request_access(cls,parent):
        cls.submit(cls.REQUEST_ACCESS,navigate=True)

    @classmethod
    def shutdown(cls):
        cls._stopping.set()
