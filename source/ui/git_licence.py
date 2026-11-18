"""Git license requests and action gate, independent of application startup."""
import queue
import threading
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox
from ..core.config import Config

class GitLicenceFlow:
    COST_WARNING = "ACHTUNG :: Es fallen monatliche Kosten an!"

    @classmethod
    def question(cls, parent, text):
        box=QMessageBox(parent)
        box.setWindowTitle("siLAssistent - Git User Lizenz")
        if "ACHTUNG ::" in text:
            import html
            formatted = html.escape(text).replace("\n", "<br>")
            formatted = formatted.replace("ACHTUNG ::", '<span style="color:#f59e0b; font-weight:700;">ACHTUNG ::</span>')
            box.setTextFormat(Qt.TextFormat.RichText)
            box.setText(formatted)
        else:
            box.setTextFormat(Qt.TextFormat.PlainText)
            box.setText(text)
        yes=box.addButton("Ja",QMessageBox.ButtonRole.YesRole)
        no=box.addButton("Nein",QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(no)
        box.setWindowModality(Qt.WindowModality.ApplicationModal)
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True)
        box.exec()
        return True if box.clickedButton() is yes else False if box.clickedButton() is no else None

    @classmethod
    def start_license_request(cls, parent):
        if getattr(parent,"_license_request",None):
            return
        messages=queue.Queue()
        timer=QTimer(parent)
        parent._license_request=(messages,timer)
        timer.timeout.connect(lambda: cls.poll_license_request(parent))
        timer.start(100)
        threading.Thread(target=cls.license_worker,args=(messages,),daemon=True).start()

    @classmethod
    def license_worker(cls, messages):
        try:
            messages.put((cls.request_license(),None))
        except Exception as error:
            messages.put((None,str(error)))

    @classmethod
    def poll_license_request(cls, parent):
        messages,timer=parent._license_request
        try:
            result,error=messages.get_nowait()
        except queue.Empty:
            return
        timer.stop()
        parent._license_request=None
        if result and result.get("license")=="present":
            Config.set_state("GitUserLicenceState",True)
            from .dialogs import Dialogs
            parent.showNormal()
            parent.raise_()
            parent.activateWindow()
            from ..stand_management.git_license import GitLicense
            try:
                Dialogs.message("Git User Lizenz vorhanden","Sie besitzen bereits eine GitHub User Licence. Ein neuer Antrag ist nicht erforderlich.",parent)
            finally:
                GitLicense.close_confirmation_browser(result)
        else:
            from .dialogs import Dialogs
            Dialogs.message("Git User Lizenz",error or result.get("reason","Lizenz konnte noch nicht bestätigt werden."),parent)

    @classmethod
    def allow_git_action(cls, window):
        if Config.state()["GitUserLicenceState"]:
            return True
        choice=cls.license_choice(window)
        if choice=="present":
            # User confirmation enables a real Git attempt; repository access is checked independently.
            Config.set_state("GitUserLicenceState",True)
            return True
        if choice=="request":
            from ..stand_management.git_window import GitWindow
            GitWindow.start(window,"license_order")
        return False

    @classmethod
    def license_choice(cls,parent):
        box=QMessageBox(parent)
        box.setWindowTitle("siLAssistent - Git User Lizenz")
        box.setText("Ihre Git User Lizenz ist in diesem Tool noch nicht bestätigt.")
        box.setInformativeText("Wenn Sie bereits eine Lizenz haben, können Sie mit der Git-Aktion fortfahren. Der Zugriff auf das Setup-Repo wird separat geprüft.\n\n"+cls.COST_WARNING)
        existing=box.addButton("Ich habe bereits eine Git User Lizenz",QMessageBox.ButtonRole.AcceptRole)
        request=box.addButton("Git User Lizenz beantragen",QMessageBox.ButtonRole.ActionRole)
        cancel=box.addButton("Abbrechen",QMessageBox.ButtonRole.RejectRole)
        from .button_gradients import ButtonGradients
        ButtonGradients.apply(existing,"#bbf7d0")
        ButtonGradients.apply(request,"#fed7aa")
        box.setDefaultButton(cancel);box.setEscapeButton(cancel)
        box.setWindowModality(Qt.WindowModality.ApplicationModal)
        box.exec()
        return "present" if box.clickedButton() is existing else "request" if box.clickedButton() is request else None

    @classmethod
    def request_license(cls):
        from ..stand_management.git_license import GitLicense
        result=GitLicense.check(visible=True)
        if result["license"]=="absent":
            return GitLicense.prepare_order()
        return result
