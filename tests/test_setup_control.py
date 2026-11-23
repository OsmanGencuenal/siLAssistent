import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from source.core.config import Config
from source.setup_operation.setup_control import SetupControl
from source.setup_operation.setup_control_window import SetupControlWindow

class SetupControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._settings_patch=patch.object(Config,"set_state")
        cls.saved_settings=cls._settings_patch.start()
        original_state=Config.state
        cls._read_settings_patch=patch.object(Config,"state",side_effect=lambda *args,**kwargs:{**original_state(*args,**kwargs),"SetupAutoConnect":False,"FlashFilesGrouped":False,"SetupHeadless":False})
        cls._read_settings_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls._read_settings_patch.stop()
        cls._settings_patch.stop()

    @classmethod
    def test_lists_only_direct_sil_files_for_selected_source(cls):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);git=root/"Git"/"SimFiles";manual=root/"Manual"/"SimFiles"
            git.mkdir(parents=True);manual.mkdir(parents=True)
            (git/"B.sil").write_text("");(git/"a.SIL").write_text("")
            (git/"notes.txt").write_text("")
            (git/"nested").mkdir();(git/"nested"/"hidden.sil").write_text("")
            (git/"directory.sil").mkdir();(manual/"manual.sil").write_text("")
            with patch.object(Config,"state",return_value={"GitLocalRepoPath":str(git),"DriveSetupLocalPath":str(manual)}):
                assert [Path(value).name for value in SetupControl.list_setups("Git")["files"]]==["a.SIL","B.sil"]
                assert [Path(value).name for value in SetupControl.list_setups("Lokale manuelle Kopie")["files"]]==["manual.sil"]

    @classmethod
    def test_unconfigured_source_is_user_friendly(cls):
        with patch.object(Config,"state",return_value={"GitLocalRepoPath":""}):
            result=SetupControl.list_setups("Git")
            assert not result["files"] and "noch kein" in result["message"]

    @classmethod
    def test_ui_switches_sources_and_radios_are_exclusive(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            git=Path(folder)/"git"/"SimFiles";manual=Path(folder)/"manual"/"SimFiles"
            git.mkdir(parents=True);manual.mkdir(parents=True)
            (git/"one.sil").write_text("");(git/"two.sil").write_text("");(manual/"manual.sil").write_text("")
            with patch.object(Config,"state",return_value={"GitLocalRepoPath":str(git),"DriveSetupLocalPath":str(manual)}):
                window=SetupControlWindow.open();state=window._setup_control
                cls.wait_for_buttons(app,state,2)
                assert [state["sources"].itemText(i) for i in range(2)]==["Git","Lokale manuelle Kopie"]
                first,second=state["group"].buttons();first.click();second.click()
                assert second.isChecked() and not first.isChecked()
                assert state["selected"]==str(git/"two.sil")
                second.click()
                assert not first.isChecked() and not second.isChecked()
                assert state["selected"] is None
                assert window.isMaximized()
                assert state["sources"].parentWidget() is state["sidebar"]
                assert state["sidebar"].width()<window.centralWidget().width()
                assert not state["workspace"].findChildren(__import__('PySide6.QtWidgets',fromlist=['QRadioButton']).QRadioButton)
                state["sources"].setCurrentIndex(1)
                cls.wait_for_buttons(app,state,1)
                assert state["group"].buttons()[0].text()=="manual.sil"
                assert state["selected"] is None
                window.close()

    @classmethod
    def wait_for_buttons(cls,app,state,count):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            app.processEvents()
            if len(state["group"].buttons())==count:return
            time.sleep(0.01)
        raise AssertionError("Setup-Dateiliste nicht rechtzeitig geladen")

    @classmethod
    def test_stale_scan_does_not_replace_current_source(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["sources"].setCurrentIndex(1)
            state["queue"].put((state["request"]-1,{"files":["old.sil"],"message":"","path":"old"},None))
            state["queue"].put((state["request"],{"files":["new.sil"],"message":"","path":"current"},None))
            SetupControlWindow.poll(window)
            assert [button.text() for button in state["group"].buttons()]==["new.sil"]
            window.close()

    @classmethod
    def test_connect_without_selection_shows_message_and_does_not_start(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"), patch("source.setup_operation.setup_control_window.Dialogs.message") as message:
            window=SetupControlWindow.open();state=window._setup_control
            state["connect"].click()
            message.assert_called_once_with("Setup auswählen","Bitte wählen Sie zuerst ein Setup aus.",window)
            assert all(isinstance(item,tuple) and item[0]=="watch" for item in list(state["commands"].queue))
            assert state["connection"].text()=="Nicht verbunden"
            window.close()

    @classmethod
    def test_connection_states_and_selection_changes(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["queue"].put((state["request"],{"files":["one.sil","two.sil"],"message":"","path":"test"},None))
            SetupControlWindow.poll(window)
            first,second=state["group"].buttons()
            first.click();second.click()
            assert not first.isChecked() and second.isChecked()
            state["connect"].click()
            assert "two.sil" in list(state["commands"].queue)
            assert state["connection"].text()=="Verbinden ..."
            assert not first.isEnabled() and not second.isEnabled()
            state["responses"].put(("connected","two.sil",None));SetupControlWindow.poll(window)
            assert state["connection"].text()=="Verbunden"
            assert "#4ade80" in state["connection"].styleSheet()
            second.click()
            assert state["selected"] is None and not any(b.isChecked() for b in state["group"].buttons())
            assert state["connection"].text()=="Nicht verbunden"
            window.close()

    @classmethod
    def test_progress_cancel_waits_for_worker_then_releases_selection(cls):
        from PySide6.QtWidgets import QApplication,QPushButton,QLabel
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="Example.sil"
            state["connect"].click()
            progress,body,animation=state["progress"]
            assert progress.isVisible()
            assert progress.findChild(QLabel,"heading").text()=="Example.sil wird ausgeführt."
            assert progress.findChild(QLabel,"progressWait").text()=="Bitte warten ..."
            cancel=next(b for b in progress.findChildren(QPushButton) if b.text()=="Abbrechen")
            cancel.click()
            assert state["cancelled"].is_set() and progress.isVisible()
            assert not state["connect"].isEnabled()
            state["responses"].put(("cancelled","Example.sil",None))
            SetupControlWindow.poll(window)
            assert not progress.isVisible() and state["progress"] is None
            assert state["connection"].text()=="Nicht verbunden" and state["connect"].isEnabled()
            window.close()

    @classmethod
    def test_progress_x_cancels_start(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="Example.sil";state["connect"].click()
            progress=state["progress"][0];progress.close()
            assert state["cancelled"].is_set()
            window.close()

    @classmethod
    def test_auto_checkbox_and_signal_displays(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            assert not state["auto"].isChecked()
            state["selected"]="one.sil";state["auto"].setChecked(True)
            assert list(state["commands"].queue)[-1]==("automatic",True,"one.sil")
            state["responses"].put(("auto","one.sil",None))
            state["responses"].put(("signals","one.sil",{"ignition":True,"engine":False}))
            SetupControlWindow.poll(window)
            assert state["ignition_state"].text()=="AN"
            assert "#4ade80" in state["ignition_state"].styleSheet()
            assert state["engine_state"].text()=="Motor steht"
            assert "#dc2626" in state["engine_state"].styleSheet()
            state["selected"]="two.sil";SetupControlWindow.watch_selection(window)
            state["responses"].put(("signals","one.sil",{"ignition":False,"engine":True}))
            SetupControlWindow.poll(window)
            assert state["engine_state"].text()=="—"
            window.close()

    @classmethod
    def test_auto_connection_failure_is_silent(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"),patch("source.setup_operation.setup_control_window.Dialogs.message") as message:
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="open.sil";state["auto"].setChecked(True)
            state["responses"].put(("auto","open.sil","Das ausgewählte Setup ist bereits geöffnet, aber seine Remote-API ist nicht erreichbar."))
            SetupControlWindow.poll(window)
            assert state["status"].text()==""
            assert state["connection"].text()=="Nicht verbunden"
            message.assert_not_called()
            window.close()

    @classmethod
    def test_simulation_warning_no_does_not_enqueue_start(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(SetupControlWindow,"ask_simulation_start",return_value=False):
            window=SetupControlWindow.open();state=window._setup_control
            assert state["mode"].currentText()=="IMO"
            state["operating"]=True
            before=list(state["commands"].queue)
            state["responses"].put(("simulation_start_required",("engine",None,"one.sil"),None))
            SetupControlWindow.poll(window)
            assert list(state["commands"].queue)==before and not state["operating"]
            window.close()

    @classmethod
    def test_simulation_warning_yes_enqueues_approved_action(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(SetupControlWindow,"ask_simulation_start",return_value=True):
            window=SetupControlWindow.open();state=window._setup_control
            state["responses"].put(("simulation_start_required",("ignition",None,"one.sil"),None))
            SetupControlWindow.poll(window)
            assert list(state["commands"].queue)[-1]==("operation","ignition",None,"one.sil",True)
            window.close()

    @classmethod
    def test_mode_start_when_disconnected_shows_loading_and_completes(cls):
        from PySide6.QtWidgets import QApplication,QLabel
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"),patch("source.setup_operation.setup_control_window.Dialogs.message") as message:
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="stopped.sil"
            SetupControlWindow.run_operation(window,"mode","IMO")
            progress=state["progress"][0]
            assert progress.isVisible()
            assert progress.findChild(QLabel,"heading").text()=="Setup wird gestartet"
            message.assert_not_called()
            state["responses"].put(("operation","stopped.sil",None))
            SetupControlWindow.poll(window)
            assert state["progress"] is None
            assert state["connected_path"]=="stopped.sil"
            assert state["connect"].isEnabled()
            window.close()

    @classmethod
    def test_ignition_off_uses_specific_large_heading(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(SetupControlWindow,"ask_ignition_start",return_value=False) as message:
            window=SetupControlWindow.open();state=window._setup_control
            state["responses"].put(("operation",None,"Zündung ist nicht AN! Motor kann nicht gestartet werden"))
            SetupControlWindow.poll(window)
            message.assert_called_once_with(window)
            window.close()

    @classmethod
    def test_disconnect_button_turns_off_auto_and_detaches(cls):
        from PySide6.QtWidgets import QApplication
        from source.silver.connection import SilverConnection
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(SilverConnection,"request_detach") as detach:
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="test.sil";state["connected_path"]="test.sil"
            state["auto"].setChecked(True)
            state["detach"].click()
            assert not state["auto"].isChecked()
            assert state["connection"].text()=="Nicht verbunden"
            detach.assert_called_once()
            assert ("disconnect",) in list(state["commands"].queue)
            state["responses"].put(("disconnected",None,None));SetupControlWindow.poll(window)
            assert not state["detaching"] and state["connect"].isEnabled()
            window.close()

    @classmethod
    def test_window_close_requests_detach_without_aborting_silver(cls):
        from PySide6.QtWidgets import QApplication
        from source.silver.connection import SilverConnection
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(SilverConnection,"request_detach") as detach,patch.object(SilverConnection,"abort_start") as abort:
            window=SetupControlWindow.open();state=window._setup_control
            window.close()
            assert state["stop"].is_set()
            detach.assert_called_once();abort.assert_not_called()

    @classmethod
    def test_cycle_visibility_and_manual_controls(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            assert state["cycle"].isHidden()
            state["mode"].setCurrentText("Zyklus")
            assert not state["cycle"].isHidden()
            for other in ("IMO","Test-Bench"):
                state["mode"].setCurrentText(other)
                assert state["cycle"].isHidden()
                state["mode"].setCurrentText("Zyklus")
                assert not state["cycle"].isHidden()
            assert [state["cycle"].itemText(i) for i in range(4)]==["NEDC","FTP75","US06","WLTP"]
            assert [state["gear"].itemText(i) for i in range(4)]==["P","R","N","D"]
            state["selected"]="test.sil";state["connected_path"]="test.sil"
            state["mode"].setCurrentText("Test-Bench")
            state["inputs"]["rpm"].setText("1200");state["inputs"]["rpm"].returnPressed.emit()
            assert list(state["commands"].queue)[-1]==("operation","inputs",{"rpm":"1200","accelerator":""},"test.sil")
            window.close()

    @classmethod
    def test_testbench_restricts_brake_and_gear_only(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            assert state["connect"].text()=="Setup :: Verbinden/Starten"
            assert state["detach"].text()=="Silver :: API-Verbindung Trennen"
            state["mode"].setCurrentText("Test-Bench")
            assert not state["gear"].isEnabled() and not state["inputs"]["brake"].isEnabled()
            assert state["inputs"]["rpm"].isEnabled() and state["inputs"]["accelerator"].isEnabled()
            for mode in ("IMO","Zyklus"):
                state["mode"].setCurrentText(mode)
                assert state["gear"].isEnabled() and state["inputs"]["brake"].isEnabled()==(mode=="IMO")
            window.close()

    @classmethod
    def test_live_inputs_preserve_user_edit_and_ignore_other_setup(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="one.sil";state["connected_path"]="one.sil"
            window.clearFocus()
            for edit in state["inputs"].values():edit.clearFocus()
            state["responses"].put(("inputs","one.sil",{"rpm":750,"accelerator":0.2,"brake":0}))
            SetupControlWindow.poll(window)
            assert state["inputs"]["rpm"].text()=="750"
            edit=state["inputs"]["rpm"];edit.setText("1234");edit.setModified(True)
            state["responses"].put(("inputs","one.sil",{"rpm":900}))
            SetupControlWindow.poll(window)
            assert edit.text()=="1234"
            state["responses"].put(("inputs","other.sil",{"accelerator":1}))
            SetupControlWindow.poll(window)
            assert state["inputs"]["accelerator"].text()=="0.2"
            window.close()

    @classmethod
    def test_focused_brake_refreshes_unedited_silver_value(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="one.sil";state["connected_path"]="one.sil"
            edit=state["inputs"]["brake"];edit.setText("1")
            with patch.object(type(edit),"hasFocus",return_value=True):
                state["responses"].put(("inputs","one.sil",{"brake":100}))
                SetupControlWindow.poll(window)
                assert edit.text()=="100"
                edit.setText("25");edit.setModified(True)
                state["responses"].put(("inputs","one.sil",{"brake":100}))
                SetupControlWindow.poll(window)
                assert edit.text()=="25"
            window.close()

    @classmethod
    def test_live_input_selection_can_be_replaced_by_typing(cls):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            try:
                state["selected"]="one.sil";state["connected_path"]="one.sil"
                for key in ("rpm","accelerator","brake"):
                    state["mode"].setCurrentText("Test-Bench" if key=="rpm" else "IMO")
                    edit=state["inputs"][key]
                    assert edit.isEnabled()
                    edit.setText("50");edit.selectAll()
                    for value in (50,60,50):
                        state["responses"].put(("inputs","one.sil",{key:value}))
                        SetupControlWindow.poll(window)
                        assert edit.selectedText()=="50"
                    QTest.keyClicks(edit,"25")
                    assert edit.text()=="25" and edit.isModified()
                    state["responses"].put(("inputs","one.sil",{key:100}))
                    SetupControlWindow.poll(window)
                    assert edit.text()=="25"
            finally:window.close()

    @classmethod
    def test_live_updates_preserve_cursor_inside_focused_input(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            try:
                state["selected"]="one.sil";state["connected_path"]="one.sil"
                for key in ("rpm","accelerator","brake"):
                    edit=state["inputs"][key];edit.setText("50");edit.setCursorPosition(1)
                    with patch.object(type(edit),"hasFocus",return_value=True):
                        for value in (50,60):
                            state["responses"].put(("inputs","one.sil",{key:value}))
                            SetupControlWindow.poll(window)
                            assert edit.text()=="50" and edit.cursorPosition()==1
            finally:window.close()

    @classmethod
    def test_operation_scrollbars_on_small_viewport(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();scroll=window._setup_control["controls_scroll"]
            scroll.setFixedSize(240,160);app.processEvents()
            assert scroll.horizontalScrollBar().maximum()>0
            assert scroll.verticalScrollBar().maximum()>0
            window.close()

    @classmethod
    def test_gear_tracks_silver_and_disabled_labels(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="one.sil";state["connected_path"]="one.sil"
            for value,gear in ((5,"D"),(-1,"R"),(0,"N"),(-2,"P")):
                state["responses"].put(("inputs","one.sil",{"gear":value}))
                SetupControlWindow.poll(window)
                assert state["gear"].currentText()==gear
            state["mode"].setCurrentText("Test-Bench")
            assert not state["gear_label"].isEnabled()
            assert not state["input_labels"]["brake"].isEnabled()
            state["mode"].setCurrentText("IMO")
            assert state["gear_label"].isEnabled() and state["input_labels"]["brake"].isEnabled()
            window.close()

    @classmethod
    def test_rpm_only_editable_in_testbench(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            for mode in ("IMO","Zyklus","Test-Bench","IMO"):
                state["mode"].setCurrentText(mode)
                assert state["inputs"]["rpm"].isEnabled()==(mode=="Test-Bench")
                assert state["input_labels"]["rpm"].isEnabled()==(mode=="Test-Bench")
            window.close()

    @classmethod
    def test_invalid_input_restores_last_confirmed_value(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"),patch("source.setup_operation.setup_control_window.Dialogs.message"):
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="one.sil";state["connected_path"]="one.sil"
            state["responses"].put(("inputs","one.sil",{"accelerator":0.3}))
            SetupControlWindow.poll(window)
            edit=state["inputs"]["accelerator"];edit.setText("20");edit.setModified(True)
            edit.returnPressed.emit()
            state["responses"].put(("operation","one.sil","Bitte einen gültigen Wert eingeben"))
            SetupControlWindow.poll(window)
            assert edit.text()=="0.3" and not edit.isModified()
            window.close()

    @classmethod
    def test_cycle_pedals_and_pause_resume(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["mode"].setCurrentText("Zyklus")
            for key in ("accelerator","brake"):
                assert not state["inputs"][key].isEnabled()
                assert not state["input_labels"][key].isEnabled()
            assert not state["pause"].isHidden()
            state["selected"]="one.sil";state["connected_path"]="one.sil"
            state["pause"].click()
            assert list(state["commands"].queue)[-1]==("operation","pause",True,"one.sil")
            assert state["pause"].text()=="Pause"
            state["responses"].put(("pause_state","one.sil",True));state["responses"].put(("operation","one.sil",None))
            SetupControlWindow.poll(window)
            assert state["pause"].text()=="Weiter"
            state["pause"].click()
            assert list(state["commands"].queue)[-1]==("operation","pause",False,"one.sil")
            state["responses"].put(("pause_state","one.sil",False));state["responses"].put(("operation","one.sil",None))
            SetupControlWindow.poll(window)
            assert state["pause"].text()=="Pause"
            state["mode"].setCurrentText("IMO")
            assert state["pause"].isHidden()
            assert state["inputs"]["accelerator"].isEnabled() and state["inputs"]["brake"].isEnabled()
            window.close()

    @classmethod
    def test_setup_checkbox_preferences_restored_and_saved(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(Config,"state",return_value={"SetupAutoConnect":True,"FlashFilesGrouped":True,"SetupHeadless":True,"SetupExitNow":True}):
            window=SetupControlWindow.open();state=window._setup_control
            assert state["auto"].isChecked() and state["parameter_panel"]._grouped.isChecked()
            assert state["headless"].isChecked() and state["exit_now"].isChecked()
            assert ("headless",True) in list(state["commands"].queue)
            window.close()
            cls.saved_settings.assert_any_call("SetupExitNow",True)
            cls.saved_settings.assert_any_call("SetupHeadless",True)
            cls.saved_settings.assert_any_call("SetupAutoConnect",True)
            cls.saved_settings.assert_any_call("FlashFilesGrouped",True)

    @classmethod
    def test_grouping_starts_enabled_even_when_previous_preference_was_false(cls):
        from source.setup_operation.parameter_files_panel import ParameterFilesPanel
        from source.silver.parameter_files import SilverParameterFiles
        from unittest.mock import Mock
        with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(Config,"state",return_value={"SetupAutoConnect":False,"FlashFilesGrouped":False,"SetupHeadless":False,"SetupExitNow":False}):
            window=SetupControlWindow.open();panel=window._setup_control["parameter_panel"]
            try:
                assert panel._grouped.isChecked()
                panel._dispatch=Mock();slave,master=SilverParameterFiles.TARGETS
                ParameterFilesPanel.populate(panel,{slave:{"files":["s.dcm"]},master:{"files":["m.dcm"]}})
                ParameterFilesPanel.change(panel,master,0,"shared.dcm");panel._flash.click()
                changes=panel._dispatch.call_args.args[1]
                assert changes[slave]==changes[master]==["shared.dcm"]
                panel._grouped.setChecked(False)
                assert not panel._grouped.isChecked()
            finally:window.close()

    @classmethod
    def test_hover_popup_uses_listview_and_green_selection(cls):
        from PySide6.QtWidgets import QApplication,QListView
        from PySide6.QtGui import QPalette
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            for combo in (state["mode"],state["gear"],state["cycle"],state["sources"]):
                assert isinstance(combo.view(),QListView)
                assert combo.view().hasMouseTracking()
                assert combo.view().palette().color(QPalette.ColorRole.Highlight).name()=="#bbf7d0"
            window.close()

    @classmethod
    def test_reselecting_connected_setup_reads_parameter_files(cls):
        import queue,threading
        from source.silver.connection import SilverConnection
        from source.silver.parameter_files import SilverParameterFiles
        commands=queue.Queue();responses=queue.Queue()
        commands.put("one.sil");commands.put(("watch",None,True));commands.put(("watch","one.sil",True));commands.put(None)
        with patch.object(SilverConnection,"connect",return_value={"reused":True}),patch.object(SilverConnection,"alive",return_value=True),patch.object(SilverConnection,"disconnect"),patch.object(SilverParameterFiles,"entries",return_value={"test":"files"}):
            SetupControlWindow.connection_loop(commands,responses,threading.Event(),threading.Event())
        assert ("parameter_files","one.sil",{"test":"files"}) in list(responses.queue)

    @classmethod
    def test_auto_toggle_keeps_connection_and_dcm_edits(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="one.sil";state["connected_path"]="one.sil"
            state["auto"].setChecked(True)
            state["parameter_panel"]._dirty.add("ECM_MRG12_Slave.sil")
            state["auto"].setChecked(False)
            assert state["connected_path"]=="one.sil"
            assert state["parameter_panel"]._dirty=={"ECM_MRG12_Slave.sil"}
            assert list(state["commands"].queue)[-1]==("automatic",False,"one.sil")
            window.close()

    @classmethod
    def test_ignition_dialog_action_queues_combined_start(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(SetupControlWindow,"ask_ignition_start",return_value=True):
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="one.sil";state["connected_path"]="one.sil"
            state["responses"].put(("operation",None,"Zündung ist nicht AN! Motor kann nicht gestartet werden"))
            SetupControlWindow.poll(window)
            assert list(state["commands"].queue)[-1]==("operation","ignition_engine",None,"one.sil")
            window.close()

    @classmethod
    def test_start_stop_state_colors(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            for active,text,color in ((True,"Aktiv","#4ade80"),(False,"Nicht aktiv","#dc2626")):
                SetupControlWindow.display_states(window,{"ignition":False,"engine":False,"start_stop":active})
                assert state["start_stop_state"].text()==text
                assert color in state["start_stop_state"].styleSheet()
            window.close()

    @classmethod
    def test_enter_submits_all_enabled_numeric_fields(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="one.sil";state["connected_path"]="one.sil"
            state["mode"].setCurrentText("IMO")
            state["inputs"]["rpm"].setText("900")
            state["inputs"]["accelerator"].setText("0.2");state["inputs"]["brake"].setText("0.5")
            state["inputs"]["brake"].returnPressed.emit()
            assert list(state["commands"].queue)[-1]==("operation","inputs",{"accelerator":"0.2","brake":"0.5"},"one.sil")
            window.close()

    @classmethod
    def test_auto_reconnect_after_explicit_disconnect_remembers_selected_setup(cls):
        import queue,threading
        from unittest.mock import Mock
        from source.silver.connection import SilverConnection
        from source.silver.parameter_files import SilverParameterFiles
        from source.silver.operation import SilverOperation
        events=iter(["one.sil",("disconnect",),("automatic",True,"one.sil"),"idle",None])
        def next_command(**kwargs):
            value=next(events)
            if value=="idle":raise queue.Empty
            return value
        commands=Mock();commands.get.side_effect=next_command;responses=queue.Queue()
        with patch.object(SilverConnection,"connect",return_value={"reused":True}) as connect,patch.object(SilverConnection,"alive",return_value=True),patch.object(SilverConnection,"disconnect"),patch.object(SilverParameterFiles,"entries",return_value={}),patch.object(SilverOperation,"states",return_value={}),patch.object(SilverOperation,"input_values",return_value={}):
            SetupControlWindow.connection_loop(commands,responses,threading.Event(),threading.Event())
            assert connect.call_count==2
            connect.assert_called_with("one.sil",allow_start=False,gui=True)
        assert ("auto","one.sil",None) in list(responses.queue)

    @classmethod
    def test_reload_button_queues_reload(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="one.sil";state["connected_path"]="one.sil"
            state["reload_setup"].click()
            assert list(state["commands"].queue)[-1]==("operation","reload",None,"one.sil")
            window.close()

    @classmethod
    def test_ignition_on_then_off_does_not_prompt_when_time_uncertain(cls):
        import queue,threading
        from source.silver.connection import SilverConnection
        from source.silver.operation import SilverOperation
        from source.silver.methods import Silver
        commands=queue.Queue();responses=queue.Queue()
        commands.put("one.sil")
        commands.put(("operation","ignition",None,"one.sil"))
        commands.put(("operation","ignition",None,"one.sil"));commands.put(None)
        value={"ignition":0}
        def write(name,v):value["ignition"]=v
        with patch.object(SilverConnection,"connect",return_value={"reused":True}),patch.object(SilverConnection,"alive",return_value=True),patch.object(SilverConnection,"disconnect"),patch.object(SilverOperation,"read",side_effect=lambda name:value["ignition"]),patch.object(SilverOperation,"write",side_effect=write),patch.object(SilverOperation,"simulation_running",return_value=None) as state,patch.object(SilverOperation,"sample_simulation_state",return_value=True):
            SetupControlWindow.connection_loop(commands,responses,threading.Event(),threading.Event())
            assert value["ignition"]==0
            assert state.call_count==2
        assert not any(item[0]=="simulation_start_required" for item in list(responses.queue))

    @classmethod
    def test_activation_initializes_rpm_field_even_with_previous_edit(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="one.sil"
            edit=state["inputs"]["rpm"];edit.setText("999");edit.setModified(True)
            state["responses"].put(("initial_rpm","one.sil",2000))
            SetupControlWindow.poll(window)
            assert edit.text()=="2000" and not edit.isModified()
            assert state["last_inputs"]["rpm"]=="2000"
            window.close()

    @classmethod
    def test_clear_errors_button_queues_api_action(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="one.sil";state["connected_path"]="one.sil"
            state["clear_errors"].click()
            assert list(state["commands"].queue)[-1]==("operation","clear_errors",None,"one.sil")
            window.close()

    @classmethod
    def test_simulation_toggle_label_and_command(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            state["selected"]="one.sil";state["connected_path"]="one.sil"
            assert state["simulation"].text()=="Simulation-Starten"
            state["responses"].put(("simulation_state","one.sil",True));SetupControlWindow.poll(window)
            assert state["simulation"].text()=="Simulation-Pausieren"
            state["responses"].put(("simulation_state","one.sil",None));SetupControlWindow.poll(window)
            assert state["simulation"].text()=="Simulation-Pausieren"
            state["simulation"].click()
            assert list(state["commands"].queue)[-1]==("operation","simulation_toggle",True,"one.sil")
            state["responses"].put(("pause_state","one.sil",True));SetupControlWindow.poll(window)
            assert state["simulation"].text()=="Simulation-Starten"
            window.close()

    @classmethod
    def test_log_has_bounded_height_and_read_only_content(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            assert state["log_view"].minimumHeight()==120 and state["log_view"].maximumHeight()>120
            assert state["log_view"].isReadOnly()
            state["mode"].setCurrentText("Test-Bench")
            assert state["log_view"].toPlainText()==""
            window.close()

    @classmethod
    def test_log_only_visible_and_writable_in_raster_mode(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            for mode in ("IMO","Test-Bench","Zyklus"):
                state["mode"].setCurrentText(mode)
                assert state["log_view"].isHidden() and state["log_heading"].isHidden()
                assert not state["log_view"].isEnabled()
                previous=state["log_view"].toPlainText()
                SetupControlWindow.append_log(window,"Nicht protokollieren")
                assert state["log_view"].toPlainText()==previous
            state["mode"].setCurrentText("Kennfeld-Rasterung")
            assert not state["log_view"].isHidden() and not state["log_heading"].isHidden()
            SetupControlWindow.append_log(window,"Rasterpunkt 1",measurement=True)
            assert "Rasterpunkt 1" in state["log_view"].toPlainText()
            window.close()

    @classmethod
    def test_initial_layout_keeps_status_rows_compact_in_tall_window(cls):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch.object(SetupControlWindow,"connection_worker"), patch.object(Config,"state",return_value={}):
            window=SetupControlWindow.open()
            try:
                window.showNormal();window.resize(1800,1200)
                for _ in range(5):app.processEvents()
                state=window._setup_control
                for button,key in zip(state["operation_buttons"][1:4],("ignition","engine","start_stop")):
                    label=state[key+"_state"]
                    assert label.height()==button.height()
                    assert label.height()<80
                assert state["manual_area"].geometry().top()<600
                assert state["controls_bottom"].isVisible()
                assert not state["log_view"].isVisible()
                for section in state["parameter_panel"]._sections.values():
                    assert section["scroll"].minimumHeight()<100
                state["mode"].setCurrentText("Kennfeld-Rasterung")
                app.processEvents()
                assert not state["controls_bottom"].isVisible()
                assert state["log_view"].isVisible()
            finally:window.close()

    @classmethod
    def test_flash_apply_shows_wait_dialog_until_worker_finishes(cls):
        from PySide6.QtWidgets import QApplication,QLabel
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"):
            window=SetupControlWindow.open();state=window._setup_control
            try:
                state["selected"]=state["connected_path"]="example.sil"
                SetupControlWindow.run_operation(window,"parameters_save",{})
                progress,body,animation=state["progress"]
                assert progress.isVisible()
                assert progress.findChild(QLabel,"progressWait").text()=="Bitte warten ..."
                assert "Datenstand" in progress.findChild(QLabel,"heading").text()
                state["responses"].put(("flash_progress","example.sil","Änderungen werden gespeichert …"))
                SetupControlWindow.poll(window)
                assert body.text()=="Änderungen werden gespeichert …"
                assert progress.isVisible()
                state["responses"].put(("operation","example.sil",None))
                SetupControlWindow.poll(window)
                assert state["progress"] is None
            finally:window.close()

    @classmethod
    def test_sections_collapse_independently_and_reflow_without_losing_values(cls):
        from itertools import product
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(Config,"state",return_value={}):
            window=SetupControlWindow.open();state=window._setup_control
            try:
                window.showNormal();window.resize(1800,1000);app.processEvents()
                state["inputs"]["accelerator"].setText("0.42")
                initial_flash=state["flash_container"].width()
                state["section_toggles"]["controls"].click();app.processEvents()
                assert state["flash_container"].width()>initial_flash
                for width,height in ((1800,1000),(1000,700),(700,500)):
                    window.resize(width,height)
                    for selection,controls,flash in product((False,True),repeat=3):
                        for key,value in (("selection",selection),("controls",controls),("flash",flash)):
                            state["section_toggles"][key].setChecked(value)
                        app.processEvents()
                        assert state["sidebar_scroll"].isVisible()==selection
                        assert state["controls_scroll"].isVisible()==controls
                        assert state["flash_container"].isVisible()==flash
                        assert state["empty_sections"].isVisible()==(not any((selection,controls,flash)))
                        assert all(button.isVisible() for button in state["section_toggles"].values())
                        assert state["inputs"]["accelerator"].text()=="0.42"
                        if selection and not controls and not flash:
                            assert state["sidebar_scroll"].width()>=window.centralWidget().width()-8
                for button in state["section_toggles"].values():button.setChecked(True)
                app.processEvents()
                assert state["controls_scroll"].widget().width()>=600
                assert state["controls_scroll"].horizontalScrollBar().maximum()>0
                assert not list(state["commands"].queue).count(("disconnect",))
            finally:window.close()
