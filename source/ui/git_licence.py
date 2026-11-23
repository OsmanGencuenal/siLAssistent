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
            formatted=formatted.replace("Es fallen monatliche Kosten an!",'<span style="color:#fda4af; font-weight:700;">Es fallen monatliche Kosten an!</span>')
            box.setTextFormat(Qt.TextFormat.RichText)
            box.setText(formatted)
        else:
            box.setTextFormat(Qt.TextFormat.PlainText)
            box.setText(text)
        yes=box.addButton("Ja",QMessageBox.ButtonRole.YesRole)
        no=box.addButton("Nein",QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(no)
        from .dialog_button_accent import DialogButtonAccent
        DialogButtonAccent.apply(box,no)
        box.setEscapeButton(no)
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
            messages.put((cls.request_license(notify=lambda notice:messages.put((notice,None))),None))
        except Exception as error:
            messages.put((None,str(error)))

    @classmethod
    def poll_license_request(cls, parent):
        if getattr(parent,"_git_profile_notice_open",False) is True:return
        messages,timer=parent._license_request
        try:
            result,error=messages.get_nowait()
        except queue.Empty:
            return
        if result and result.get("license")=="profile_verification_required":
            cls.profile_notice(parent,result)
            return
        if result and result.get("license")=="checkout_required":
            cls.checkout_notice(parent)
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
            parent.showNormal();parent.raise_();parent.activateWindow()
            Dialogs.message("Git User Lizenz – Bestellung prüfen" if result and result.get("license")=="review" else "Git User Lizenz",error or (result or {}).get("reason","Lizenz konnte noch nicht bestätigt werden."),parent)

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
    def request_license(cls,notify=None):
        from ..stand_management.git_license import GitLicense
        options={"notify":notify} if notify is not None else {}
        result=GitLicense.check(visible=True,for_order=True,**options)
        if result["license"]=="absent":
            browser=result.pop("_browser",None)
            options={"driver":browser} if browser is not None else {}
            if notify is not None:options["notify"]=notify
            return GitLicense.prepare_order(**options)
        return result

    @classmethod
    def checkout_notice(cls,parent):
        from .dialogs import Dialogs
        from ..stand_management.git_license import GitLicense
        parent.showNormal();parent.raise_();parent.activateWindow()
        Dialogs.message("Git User Lizenz – Checkout",GitLicense.CHECKOUT_MESSAGE,parent)


    @classmethod
    def profile_notice(cls,parent,result):
        from .dialogs import Dialogs
        from .button_gradients import ButtonGradients
        from PySide6.QtWidgets import QPushButton,QLabel,QFrame,QVBoxLayout,QHBoxLayout
        dialog,footer,body=Dialogs.card('E-Mail bestätigen und fortfahren','',parent)
        dialog.setWindowTitle('siLAssistent - Git User Lizenz')
        body.setText('Developer Compass benötigt zuerst die Bestätigung Ihrer E-Mail-Adresse.')
        body.setStyleSheet("color:#f9a8d4; font:700 18pt 'Segoe UI';")
        message=body.parentWidget().layout();index=message.indexOf(body)+1
        steps=(("ZU IHREM E-MAIL-POSTFACH WECHSELN","Öffnen Sie die E-Mail von Developer Compass mit dem Betreff „Verify Email address“.","#40e0d0"),
               ("E-MAIL-ADRESSE BESTÄTIGEN","Klicken Sie in dieser E-Mail auf „Confirm my email address“.","#86efac"),
               ("ZUM TOOL ZURÜCKKEHREN","Wechseln Sie danach zurück zu siLAssistent und klicken Sie unten auf „Bestätigt – weiter“.","#ffffff"))
        for number,(title,description,color) in enumerate(steps,1):
            card=QFrame();card.setObjectName('compassProfileStep'+str(number))
            appearance='background:#29293d; border:1px solid #475569;'
            if number==3:appearance='background:#183d43; border:2px solid #40e0d0; border-left:6px solid #40e0d0;'
            card.setStyleSheet('QFrame#'+card.objectName()+' {'+appearance+' border-radius:6px;}')
            content=QVBoxLayout(card);content.setContentsMargins(18,16,18,16);content.setSpacing(10)
            heading=QLabel(str(number)+'  '+title);heading.setWordWrap(True)
            heading.setStyleSheet(f"border:0; background:transparent; color:{color}; font:700 15pt 'Segoe UI';")
            description_label=QLabel(description);description_label.setWordWrap(True)
            weight=700 if number==3 else 400
            description_label.setStyleSheet(f"border:0; background:transparent; color:#ffffff; font:{weight} 14pt 'Segoe UI';")
            content.addWidget(heading);content.addWidget(description_label)
            message.insertWidget(index,card);index+=1
        note=QLabel('Der Assistent setzt anschließend die Lizenzprüfung und den Antrag fort.');note.setWordWrap(True)
        note.setStyleSheet("color:#cbd5e1; font:13pt 'Segoe UI';")
        message.insertWidget(index,note)
        proceed=QPushButton('Bestätigt – weiter');ButtonGradients.apply(proceed,'#99f6e4',padding='12px 24px',font="700 14pt 'Segoe UI'")
        later=QPushButton('Später fortsetzen');ButtonGradients.apply(later,'#dc2626',padding='10px 18px',font="700 13pt 'Segoe UI'")
        proceed.clicked.connect(dialog.accept);later.clicked.connect(dialog.reject)
        buttons=QHBoxLayout();buttons.addWidget(later);buttons.addStretch();buttons.addWidget(proceed)
        footer.addLayout(buttons)
        dialog.resize(min(840,dialog.maximumWidth()),min(850,dialog.maximumHeight()))
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        # Do not pin over Outlook: the user must be able to read their mail.
        QTimer.singleShot(0,lambda:Dialogs.foreground(dialog))
        parent._git_profile_notice_open=True
        try:accepted=dialog.exec()==1
        finally:parent._git_profile_notice_open=False
        result['resume' if accepted else 'cancel'].set()
