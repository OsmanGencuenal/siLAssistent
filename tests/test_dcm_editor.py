import tempfile
from pathlib import Path
from unittest.mock import patch
from source.setup_operation.dcm_editor import DcmEditor
from source.core.config import Config

def test_remembered_editor_gets_dcm_as_separate_argument():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);dcm=root/"file.dcm";dcm.write_text("")
        editor=root/"notepad++.exe";editor.write_text("")
        with patch.object(Config,"state",return_value={"DcmEditorPath":str(editor)}),patch.object(DcmEditor,"choose") as choose,patch("source.setup_operation.dcm_editor.QProcess.startDetached",return_value=(True,1)) as launch:
            DcmEditor.open("file.dcm",str(root/"setup.sil"),None)
            launch.assert_called_once_with(str(editor),[str(dcm)])
            choose.assert_not_called()

def test_editor_list_choice_is_remembered_without_file_browser():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication,QListWidget,QCheckBox,QDialog
    app=QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        editor=Path(folder)/"notepad++.exe";editor.write_text("")
        def choose_first():
            dialog=app.activeModalWidget()
            dialog.findChild(QListWidget,"editorList").setCurrentRow(0)
            dialog.findChild(QCheckBox,"rememberEditor").setChecked(True)
            dialog.accept()
        with patch.object(DcmEditor,"installed_editors",return_value=[("Notepad++",str(editor))]),patch.object(Config,"set_state") as save,patch("source.setup_operation.dcm_editor.QFileDialog.getOpenFileName") as browse:
            QTimer.singleShot(0,choose_first)
            assert DcmEditor.choose(None)==str(editor)
            save.assert_called_once_with("DcmEditorPath",str(editor))
            browse.assert_not_called()
