"""Colour-matched button frames, applied as buttons become visible."""
import re
from PySide6.QtCore import QObject,QEvent
from PySide6.QtGui import QColor,QPalette
from PySide6.QtWidgets import QApplication,QPushButton,QToolButton

class ButtonFrames(QObject):
    _filter=None
    _counter=0

    @classmethod
    def install(cls):
        app=QApplication.instance()
        if app is not None and cls._filter is None:
            cls._filter=QObject(app)
            cls._filter.eventFilter=lambda watched,event:cls.filter_event(watched,event)
            app.installEventFilter(cls._filter)

    @classmethod
    def filter_event(cls,watched,event):
        if event.type()==QEvent.Type.Show and isinstance(watched,(QPushButton,QToolButton)):
            cls.decorate(watched)
        return False

    @classmethod
    def decorate(cls,button):
        if button.text().strip()=="Launcher" and not button.property("launcherButtonStyle"):
            from .button_gradients import ButtonGradients
            ButtonGradients.launcher(button)
        if button.property("suiteButtonFrame"):return
        button.setProperty("suiteButtonFrame",True)
        style=button.styleSheet()
        backgrounds=re.findall(r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{6})",style)
        color=QColor(backgrounds[0]) if backgrounds else button.palette().color(QPalette.ColorRole.Button)
        hue=color.hsvHue()
        if button.text()=="Übernehmen" or (15<=hue<=45 and color.value()>180):border="#f59e0b"
        elif color.hsvSaturation()<35:border="#64748b"
        else:border=color.darker(135).name()
        owner=button
        policy=None
        while owner is not None:
            policy=owner.property("buttonFramePolicy")
            if policy:break
            owner=owner.parentWidget()
        no_border=False
        if policy=="navy":border="#172554"
        elif policy=="launcher":
            border="#40e0d0";no_border=button.objectName()!="setupButton"
        name=button.objectName()
        if not name:
            cls._counter+=1;name="suiteFramedButton"+str(cls._counter);button.setObjectName(name)
        selector=("QToolButton" if isinstance(button,QToolButton) else "QPushButton")+"#"+name
        if style.strip() and "{" not in style:style=selector+" {"+style+"}"
        frame="0" if no_border else f"2px solid {border}"
        disabled="" if no_border else f" {selector}:disabled {{border-color:#475569;}}"
        button.setStyleSheet(style+f"\n{selector} {{border:{frame}; border-radius:4px;}}"+disabled)
