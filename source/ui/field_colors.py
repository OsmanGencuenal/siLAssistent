"""Colour concept 1: subtle section backgrounds and light value fields."""
from PySide6.QtWidgets import QFrame,QGroupBox

class FieldColors:
    COLORS={"rpm":("#bfdbfe","#60a5fa","#233049"),"accelerator":("#bbf7d0","#4ade80","#23382f"),"pedal":("#bbf7d0","#4ade80","#23382f"),"brake":("#fecaca","#fb7185","#3d2933"),"gear":("#fed7aa","#f59e0b","#3a3029"),"time":("#e9d5ff","#c084fc","#31283f")}

    @classmethod
    def card(cls,key):
        light,accent,dark=cls.COLORS[key]
        card=QFrame();card.setObjectName("fieldCard_"+key)
        card.setStyleSheet(f"QFrame#fieldCard_{key} {{background:{dark}; border:1px solid {accent}; border-radius:6px;}} QFrame#fieldCard_{key}:disabled {{background:#30303e; border-color:#51586a;}}")
        return card

    @classmethod
    def heading(cls,key):
        return "QLabel {background:transparent; border:0; color:"+cls.COLORS[key][1]+"; font:700 13pt 'Segoe UI';} QLabel:disabled {color:#8892a5;}"

    @classmethod
    def field(cls,key,kind="QLineEdit"):
        light,accent,dark=cls.COLORS[key]
        return (f"{kind} {{background:#ffffff; color:#172554; border:1px solid {accent}; border-radius:4px; padding:5px; font-weight:600; selection-background-color:#172554; selection-color:#ffffff;}} "
                f"{kind}:disabled {{background:#30303e; color:#8892a5; border-color:#51586a;}} "
                + ("QLineEdit {placeholder-text-color:#64748b;}" if kind=="QLineEdit" else ""))

    @classmethod
    def group(cls,title,key):
        light,accent,dark=cls.COLORS[key]
        group=QGroupBox(title)
        group.setStyleSheet(f"QGroupBox {{background:{dark}; color:{accent}; font:700 13pt 'Segoe UI'; border:1px solid {accent}; border-radius:6px; padding-top:23px; margin-top:9px;}} QGroupBox::title {{subcontrol-origin:margin; left:10px; padding:0 4px;}} QLabel {{color:#cbd5e1; font:10pt 'Segoe UI';}}")
        return group
