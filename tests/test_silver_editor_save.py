from unittest.mock import Mock
from source.silver.editor_save import SilverEditorSave

def test_only_scoped_module_changed_save_is_invoked():
    desktop=Mock();dialog=Mock()
    save=Mock();save.window_text.return_value="Save";save.is_enabled.return_value=True
    discard=Mock();discard.window_text.return_value="Discard"
    dialog.descendants.return_value=[save,discard];desktop.windows.return_value=[dialog]
    assert SilverEditorSave.save_dialogs(desktop,[42])==1
    desktop.windows.assert_called_once_with(process=42,title="Module Changed",visible_only=True)
    save.invoke.assert_called_once();discard.invoke.assert_not_called()

def test_ambiguous_save_buttons_are_not_clicked():
    desktop=Mock();dialog=Mock();button=Mock();button.window_text.return_value="Save"
    desktop.windows.return_value=[dialog];dialog.descendants.return_value=[button,button]
    assert SilverEditorSave.save_dialogs(desktop,[42])==0
    button.invoke.assert_not_called()

def test_native_save_button_uses_windows_message_click():
    desktop=Mock();dialog=Mock();button=Mock()
    button.window_text.return_value="&Save";button.is_enabled.return_value=True
    desktop.windows.return_value=[dialog];dialog.descendants.return_value=[button]
    assert SilverEditorSave.save_dialogs(desktop,[10460],native=True)==1
    dialog.descendants.assert_called_once_with(class_name="Button")
    button.click.assert_called_once();button.invoke.assert_not_called()


def test_editor_is_left_before_api_changes_without_screen_coordinates():
    desktop=Mock();window=Mock();gui=Mock();sfu=Mock()
    gui.window_text.return_value="GUI (129)";gui.is_selected.return_value=True
    sfu.window_text.return_value="ECM_MRG12_Slave.sil (3754)"
    window.descendants.return_value=[sfu,gui]
    desktop.windows.side_effect=[[window],[]]
    SilverEditorSave.clear_on_desktop(desktop,42)
    gui.select.assert_called_once();sfu.select.assert_not_called()


def test_ambiguous_gui_tree_does_not_switch_other_modules():
    import pytest
    desktop=Mock();window=Mock();gui=Mock();gui.window_text.return_value="GUI (129)"
    window.descendants.return_value=[gui,gui];desktop.windows.return_value=[window]
    with pytest.raises(RuntimeError,match="eindeutig"):
        SilverEditorSave.clear_on_desktop(desktop,42)
    gui.select.assert_not_called()
