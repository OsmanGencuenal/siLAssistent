import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtWidgets import QApplication,QPushButton
from source.ui.button_frames import ButtonFrames

def test_visible_buttons_get_matching_frame_once():
    app=QApplication.instance() or QApplication([])
    ButtonFrames.install()
    button=QPushButton("Übernehmen");button.setStyleSheet("background:#fed7aa; color:#172554;")
    button.show();app.processEvents()
    assert "border:2px solid #f59e0b" in button.styleSheet()
    original=button.styleSheet();button.hide();button.show();app.processEvents()
    assert button.styleSheet()==original
    button.close()

def test_launcher_has_only_turquoise_setup_frame_and_setup_tools_navy():
    from PySide6.QtWidgets import QWidget
    app=QApplication.instance() or QApplication([])
    launcher=QWidget();launcher.setProperty("buttonFramePolicy","launcher")
    setup=QPushButton("SiL-Einrichten",launcher);setup.setObjectName("setupButton")
    other=QPushButton("Git",launcher)
    for button in (setup,other):ButtonFrames.decorate(button)
    assert "border:2px solid #40e0d0" in setup.styleSheet()
    assert "border:0;" in other.styleSheet()
    tool=QWidget();tool.setProperty("buttonFramePolicy","navy")
    apply=QPushButton("Übernehmen",tool);ButtonFrames.decorate(apply)
    assert "border:2px solid #172554" in apply.styleSheet()
    launcher.close();tool.close()


def test_message_boxes_outline_yes_without_changing_default_no():
    from PySide6.QtWidgets import QMessageBox
    app=QApplication.instance() or QApplication([]);ButtonFrames.install()
    box=QMessageBox();box.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    yes=box.button(QMessageBox.StandardButton.Yes);no=box.button(QMessageBox.StandardButton.No)
    box.show();app.processEvents()
    assert yes.property("dialogAccent") and "#40e0d0" in yes.styleSheet()
    assert not no.property("dialogAccent")
    from PySide6.QtTest import QTest
    QTest.qWait(50)
    image=yes.grab().toImage()
    assert any(image.pixelColor(x,y).name()=="#40e0d0" for x in range(image.width()) for y in range(min(3,image.height())))
    assert box.defaultButton() is no
    yes.click();assert box.clickedButton() is yes
    box.deleteLater();app.processEvents()


def test_exit_confirmation_retains_explicit_no_outline():
    from PySide6.QtWidgets import QMessageBox
    app=QApplication.instance() or QApplication([]);ButtonFrames.install()
    box=QMessageBox();yes=box.addButton("Yes",QMessageBox.ButtonRole.YesRole)
    no=box.addButton("No",QMessageBox.ButtonRole.NoRole);no.setObjectName("exitNo");box.setDefaultButton(no)
    box.show();app.processEvents()
    assert no.property("dialogAccent") and not yes.property("dialogAccent")
    no.click();assert box.clickedButton() is no
    box.deleteLater();app.processEvents()
