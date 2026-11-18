import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtWidgets import QApplication,QCheckBox
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from source.ui.checkboxes import Checkboxes

def test_click_unused_checkbox_background_toggles_both_ways():
    app=QApplication.instance() or QApplication([])
    for title in ("Automatisch Verbinden","Gruppieren"):
        checkbox=Checkboxes.full_click(QCheckBox(title))
        checkbox.setStyleSheet("background:#fed7aa; padding:8px 12px;")
        checkbox.resize(460,42);checkbox.show();app.processEvents()
        point=QPoint(checkbox.width()-4,checkbox.height()//2)
        QTest.mouseClick(checkbox,Qt.MouseButton.LeftButton,pos=point)
        assert checkbox.isChecked()
        QTest.mouseClick(checkbox,Qt.MouseButton.LeftButton,pos=point)
        assert not checkbox.isChecked()
        checkbox.close()
