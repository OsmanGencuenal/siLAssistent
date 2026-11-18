import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from unittest.mock import patch,call
import pytest
from source.silver.operation import SilverOperation as Op


def test_defaults_are_read_from_mapping_constants():
    with patch.object(Op,"read",side_effect=[60,70,80]) as read:
        assert Op.init_defaults()=={"T_Engine":60,"T_Oil":70,"T_WaterEngine":80}
        assert read.call_args_list==[call("mapping.mdl."+name+"_const") for name in Op.INIT_TEMPERATURES]


@pytest.mark.parametrize("running",[True,False])
def test_selected_values_only_and_original_running_state(running):
    with patch.object(Op,"simulation_running",return_value=running),patch.object(Op,"write") as write,patch.object(Op,"read",side_effect=lambda name:{"T_Engine":100.9,"T_WaterEngine":49.6}[name]),patch.object(Op,"set_paused") as paused:
        Op.set_init_values({"T_Engine":100,"T_WaterEngine":50})
        writes=write.call_args_list
        assert writes[:2]==[call("mapping.mdl.T_Engine_const",100),call("mapping.mdl.T_WaterEngine_const",50)]
        assert call("mapping.mdl.T_Engine_mode",0) in writes
        assert call("mapping.mdl.T_Engine_mode",2) in writes
        assert call("mapping.mdl.T_WaterEngine_mode",2) in writes
        assert all("T_Oil" not in args.args[0] for args in writes)
        assert paused.call_args_list==([] if running else [call(False),call(True)])


def test_failed_initialization_restores_model_modes_and_pauses():
    with patch.object(Op,"simulation_running",return_value=False),patch.object(Op,"write") as write,patch.object(Op,"read",side_effect=RuntimeError("read failed")),patch.object(Op,"set_paused") as paused:
        with pytest.raises(RuntimeError,match="read failed"):Op.set_init_values({"T_Engine":60})
        assert write.call_args_list[-1]==call("mapping.mdl.T_Engine_mode",2)
        assert paused.call_args_list==[call(False),call(True)]


def test_outside_tolerance_does_not_return_to_model_early():
    with patch.object(Op,"simulation_running",return_value=True),patch.object(Op,"write") as write,patch.object(Op,"read",side_effect=[102,100.5]) as read,patch("source.silver.operation.time.sleep"):
        Op.set_init_values({"T_Engine":100})
        assert read.call_count==2
        assert write.call_args_list[-1]==call("mapping.mdl.T_Engine_mode",2)


def test_invalid_values_do_not_write_or_start_simulation():
    with patch.object(Op,"write") as write,patch.object(Op,"simulation_running") as running:
        for values in ({},{"Other":1},{"T_Engine":float("nan")}):
            with pytest.raises(ValueError):Op.set_init_values(values)
        write.assert_not_called();running.assert_not_called()


def test_dialog_uses_current_defaults_and_submits_only_checked_values():
    from PySide6.QtWidgets import QApplication,QWidget,QCheckBox,QDoubleSpinBox
    from source.setup_operation.init_values_dialog import InitValuesDialog as Dialog
    app=QApplication.instance() or QApplication([]);owner=QWidget();sent=[]
    with patch("source.setup_operation.init_values_dialog.Dialogs.foreground"):
        dialog=Dialog.open(owner,{"T_Engine":60,"T_Oil":70,"T_WaterEngine":80},sent.append)
        try:
            fields={name:(dialog.findChild(QCheckBox,"initSelect_"+name),dialog.findChild(QDoubleSpinBox,"initValue_"+name)) for name in Op.INIT_TEMPERATURES}
            assert all(not check.isChecked() and not edit.isEnabled() for check,edit in fields.values())
            assert fields["T_Oil"][1].value()==70
            fields["T_Oil"][0].setChecked(True);fields["T_Oil"][1].setValue(90)
            Dialog.submit(dialog,fields,sent.append)
            assert sent==[{"T_Oil":90}]
        finally:dialog.close();owner.close()
