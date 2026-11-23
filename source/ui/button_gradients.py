"""Dark gradients for setup controls, retaining each action's colour family."""
from PySide6.QtGui import QColor,QIcon,QPainter

class ButtonGradients:
    COLORS={
        "jira_request":("#169c50","#086637","#74e8a0"),
        "support":("#743b4d","#382431","#ecc1cd"),
        "#86efac":("#347a5c","#194936","#86efac"),
        "#172554":("#234579","#101f42","#7096cb"),
        "#99f6e4":("#258d91","#15535e","#89e5e4"),
        "#bbf7d0":("#347a5c","#194936","#bbf7d0"),
        "#fecaca":("#995568","#542c3b","#fecaca"),
        "#fca5a5":("#99505b","#572935","#fca5a5"),
        "#bfdbfe":("#416f9d","#233b64","#bfdbfe"),
        "#f59e0b":("#a16b20","#604014","#f59e0b"),
        "#fde68a":("#a68a35","#665321","#fde68a"),
        "#dc2626":("#b3333e","#651d2b","#ef717a"),
        "#fed7aa":("#9a724a","#58412e","#fed7aa"),
        "#facc15":("#a88a22","#625112","#facc15"),
        "#2a2a3e":("#414157","#272737","#64748b"),
    }

    @classmethod
    def launcher(cls,button):
        from PySide6.QtCore import Qt
        cls.apply(button,"#99f6e4",padding="6px 12px")
        button.setMinimumHeight(36)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("launcherButtonStyle",True)

    @classmethod
    def rule(cls,base):
        start,end,border=cls.COLORS[base]
        return (f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {start},stop:1 {end});"
                f"color:#ffffff; border:1px solid {border}; border-top:2px solid {QColor(border).lighter(110).name()};")

    @classmethod
    def apply(cls,button,base,padding=None,font=None,checked=None):
        selector=button.metaObject().className()
        extra=(f"padding:{padding};" if padding else "")+(f"font:{font};" if font else "font-weight:700;")
        style=f"{selector} {{{cls.rule(base)} border-radius:5px; {extra}}}"
        if checked:style+=f" {selector}:checked {{{cls.rule(checked)}}}"
        style+=f" {selector}:hover {{border-color:#f1f5f9;}} {selector}:pressed {{background:{cls.COLORS[base][1]};}}"
        style+=f" {selector}:focus {{border:2px solid #e2e8f0;}}"
        style+=f" {selector}:disabled {{background:#343440; color:#9399a8; border:1px solid #55596a;}}"
        button.setProperty("suiteButtonFrame",True)
        button.setStyleSheet(style)
        # Existing folder/editor glyphs are dark; recolour their alpha for dark buttons.
        if hasattr(button,"icon") and not button.icon().isNull() and not button.property("gradientIcon"):
            original=button.icon();icon=QIcon()
            for size in original.availableSizes() or [button.iconSize()]:
                pixmap=original.pixmap(size)
                painter=QPainter(pixmap);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                painter.fillRect(pixmap.rect(),QColor("#ffffff"));painter.end();icon.addPixmap(pixmap)
            button.setIcon(icon);button.setProperty("gradientIcon",True)
