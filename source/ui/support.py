"""Support Outlook draft; never send mail automatically."""
import configparser
import re
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
from ..core.config import Config

class Support:
    @classmethod
    def recipient(cls):
        path=Config.ensure_state()
        address=Config.parser(path).get("APPLICATION","supportMail",fallback="").strip()
        if not address:
            parser=configparser.ConfigParser(interpolation=None)
            parser.read(Config.load()["update_ini_path"],encoding="utf-8-sig")
            Config.sync_support_mail(parser,path)
            address=Config.parser(path).get("APPLICATION","supportMail",fallback="").strip()
        if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",address):
            raise ValueError("In der lokalen INI unter [APPLICATION] fehlt eine gültige supportMail-Adresse.")
        return address

    @classmethod
    def compose(cls,recipient):
        import win32com.client
        outlook=win32com.client.Dispatch("Outlook.Application")
        message=outlook.CreateItem(0)
        message.To=recipient;message.Subject="M286-SIL :: "
        message.Display(False)
        inspector=message.GetInspector
        inspector.Activate()
        QTimer.singleShot(200,lambda:cls.foreground(inspector))

    @classmethod
    def foreground(cls,inspector,attempt=0):
        """Activate only this draft once its native window exists; never pin it on top."""
        import logging
        import pythoncom
        import win32api
        import win32con
        import win32gui
        import win32process
        try:
            try:
                handle=int(inspector._oleobj_.QueryInterface(pythoncom.IID_IOleWindow).GetWindow())
            except Exception:
                handle=int(inspector.WordEditor.Windows.Item(1).Hwnd)
            if not handle or not win32gui.IsWindow(handle):
                raise RuntimeError("Outlook-Nachrichtenfenster ist noch nicht bereit.")
        except Exception:
            if attempt<9:
                QTimer.singleShot(200,lambda:cls.foreground(inspector,attempt+1))
            else:logging.getLogger(__name__).warning("Outlook-Nachrichtenfenster konnte nicht ermittelt werden.",exc_info=True)
            return
        attached=[]
        current=win32api.GetCurrentThreadId()
        try:
            foreground=win32gui.GetForegroundWindow()
            targets={win32process.GetWindowThreadProcessId(handle)[0]}
            if foreground:targets.add(win32process.GetWindowThreadProcessId(foreground)[0])
            for target in targets-{current}:
                win32process.AttachThreadInput(current,target,True)
                attached.append(target)
            if win32gui.IsIconic(handle):win32gui.ShowWindow(handle,win32con.SW_RESTORE)
            win32gui.BringWindowToTop(handle)
            win32gui.SetForegroundWindow(handle)
        except Exception:
            logging.getLogger(__name__).warning("Outlook-Nachrichtenfenster konnte nicht aktiviert werden.",exc_info=True)
        finally:
            for target in reversed(attached):
                win32process.AttachThreadInput(current,target,False)

    @classmethod
    def open(cls,parent=None):
        try:address=cls.recipient()
        except (OSError,ValueError,configparser.Error) as error:
            QMessageBox.warning(parent,"Supportadresse fehlt",str(error));return
        try:cls.compose(address)
        except Exception:QMessageBox.warning(parent,"Outlook","Die Supportnachricht konnte nicht geöffnet werden. Bitte Outlook prüfen.")
