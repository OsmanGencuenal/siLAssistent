"""Consistent non-native combo popups with a visible hover highlight."""
from PySide6.QtWidgets import QListView,QStyledItemDelegate
from PySide6.QtGui import QPalette,QColor

class ComboBoxes:
    @classmethod
    def configure(cls,combo):
        view=QListView(combo)
        view.setMouseTracking(True);view.viewport().setMouseTracking(True)
        view.setItemDelegate(QStyledItemDelegate(view))
        view.setStyleSheet("QListView {background:#1e1e2e; color:#e2e8f0; selection-background-color:#bbf7d0; selection-color:#172554;} QListView::item {padding:6px;} QListView::item:hover, QListView::item:selected {background:#bbf7d0; color:#172554;}")
        palette=view.palette()
        for group in (QPalette.ColorGroup.Active,QPalette.ColorGroup.Inactive):
            palette.setColor(group,QPalette.ColorRole.Highlight,QColor("#bbf7d0"))
            palette.setColor(group,QPalette.ColorRole.HighlightedText,QColor("#172554"))
        view.setPalette(palette);combo.setView(view)
