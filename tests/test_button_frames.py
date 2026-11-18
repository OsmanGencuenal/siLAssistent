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
