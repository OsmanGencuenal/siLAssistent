import os,threading
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from unittest.mock import patch,call
import pytest
from source.silver.map_sweep import MapSweep
from source.silver.operation import SilverOperation as Op
from source.silver.methods import Silver

SETTINGS={"rpm_from":1000,"rpm_to":1100,"rpm_step":100,"pedal_from":.2,"pedal_to":.4,"pedal_step":.2,"dwell":2}

def test_axes_include_end_once_even_when_step_does_not_divide_range():
    assert MapSweep.axis(1000,1250,100)==[1000,1100,1200,1250]
    assert MapSweep.axis(20,40,20)==[20,40]
    assert MapSweep.axis(1000,1000,100)==[1000]
    assert MapSweep.axis(20.1,20.3,.1)==[20.1,20.2,20.3]

def test_invalid_settings_fail_before_any_silver_calls():
    with patch.object(Op,"start_mode") as start:
        for changes in ({"pedal_to":101},{"rpm_step":0},{"rpm_to":900},{"dwell":0},{"rpm_from":float("nan")}):
            with pytest.raises(ValueError):MapSweep.run({**SETTINGS,**changes},lambda msg:None)
        start.assert_not_called()

def test_sweep_initializes_testbench_then_drives_all_points_in_order():
    log=[]
    with patch.object(Op,"start_mode") as start,patch.object(Op,"write") as write,patch.object(Op,"set_inputs") as points,patch.object(MapSweep,"wait_simulation") as wait,patch.object(Op,"read",side_effect=lambda name:1000 if name=="n_EngineSpeed" else .2):
        MapSweep.run(SETTINGS,log.append)
        start.assert_called_once_with("Test-Bench",None)
        assert points.call_args_list==[call({"rpm":1000,"accelerator":.2}),call({"rpm":1000,"accelerator":.4}),call({"rpm":1100,"accelerator":.2}),call({"rpm":1100,"accelerator":.4})]
        assert wait.call_args_list==[call(seconds,None,None) for _ in range(4) for seconds in (1.5,2)]
        assert write.call_args_list[-1]==call(Op.PREFIX+"pos_AcceleratorPedal_const",0)
    assert len(log)==8
    assert log[-1]=="Drehzahl: 1100 rpm | Pedal: 0.4 | HW__ICE__CrkShftTq_M: 0.2"

def test_wait_uses_simulation_time_not_wall_sleep():
    with patch.object(Silver,"get_time",side_effect=[2,2.5,3.5]),patch("source.silver.map_sweep.time.sleep"):
        MapSweep.wait_simulation(1.5)

def test_paused_simulation_has_bounded_stall_wait():
    with patch.object(Silver,"get_time",return_value=1),patch("source.silver.map_sweep.time.monotonic",side_effect=[0,16]):
        with pytest.raises(RuntimeError,match="Simulationszeit steht"):MapSweep.wait_simulation(1.5)

def test_cancel_stops_wait_and_restores_accelerator():
    event=threading.Event()
    def cancel(*args):event.set();MapSweep.check_cancel(event,None)
    with patch.object(Op,"start_mode"),patch.object(Op,"write") as write,patch.object(Op,"set_inputs"),patch.object(MapSweep,"wait_simulation",side_effect=cancel):
        with pytest.raises(RuntimeError,match="abgebrochen"):MapSweep.run(SETTINGS,lambda msg:None,event)
        assert write.call_args_list[-1]==call(Op.PREFIX+"pos_AcceleratorPedal_const",0)

def test_sweep_mode_replaces_manual_fields_and_logs():
    from PySide6.QtWidgets import QApplication
    from source.setup_operation.setup_control_window import SetupControlWindow as Window
    from source.core.config import Config
    app=QApplication.instance() or QApplication([])
    with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(Config,"set_state"):
        window=Window.open();state=window._setup_control
        state["mode"].setCurrentText("Kennfeld-Rasterung")
        assert state["manual_area"].isHidden() and not state["sweep_panel"].isHidden()
        state["selected"]="one.sil";state["connected_path"]="one.sil"
        Window.start_selected_mode(window)
        assert list(state["commands"].queue)[-1][1]=="sweep"
        assert state["sweep_panel"].cancel.isEnabled()
        state["responses"].put(("log","one.sil","Punkt 1 gefahren"));Window.poll(window)
        assert "Punkt 1 gefahren" in state["log_view"].toPlainText()
        state["sweep_panel"].cancel.click();assert state["sweep_cancel"].is_set()
        state["responses"].put(("operation","one.sil",None));Window.poll(window)
        state["mode"].setCurrentText("IMO")
        assert not state["manual_area"].isHidden() and state["sweep_panel"].isHidden()
        window.close()

def test_normalized_pedal_is_not_divided_by_100_and_settle_is_configurable():
    config={**SETTINGS,"rpm_to":1000,"pedal_from":.1,"pedal_to":1,"pedal_step":.2,"settle":2.5}
    with patch.object(Op,"start_mode"),patch.object(Op,"write"),patch.object(Op,"set_inputs") as points,patch.object(MapSweep,"wait_simulation") as wait,patch.object(Op,"read",return_value=1000):
        MapSweep.run(config,lambda message:None)
        assert [item.args[0]["accelerator"] for item in points.call_args_list]==[.1,.3,.5,.7,.9,1]
        assert wait.call_args_list[0]==call(2.5,None,None)

def test_raster_fields_use_dot_and_default_settle():
    from PySide6.QtWidgets import QApplication
    from source.setup_operation.map_sweep_panel import MapSweepPanel
    app=QApplication.instance() or QApplication([])
    panel=MapSweepPanel.create()
    assert panel.fields["settle"].value()==1.5
    for field in panel.fields.values():assert field.locale().decimalPoint()=="."
    assert panel.fields["pedal_to"].maximum()==1
    panel.close()

def test_cancel_message_is_informational_and_restores_controls():
    from PySide6.QtWidgets import QApplication
    from source.setup_operation.setup_control_window import SetupControlWindow as Window
    from source.core.config import Config
    app=QApplication.instance() or QApplication([])
    with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(Config,"set_state"),patch("source.setup_operation.setup_control_window.Dialogs.message") as message:
        window=Window.open();state=window._setup_control
        state["pending_action"]="sweep";state["operating"]=True
        state["responses"].put(("sweep_cancelled",None,"Kennfeld-Rasterung abgebrochen."))
        Window.poll(window)
        message.assert_called_once_with("Kennfeld-Rasterung abgebrochen","Die Rasterung wurde auf Ihren Wunsch beendet.",window)
        assert not state["operating"] and state["mode"].isEnabled()
        window.close()


def test_requested_pause_does_not_trigger_stall_timeout():
    from unittest.mock import Mock
    control=Mock(side_effect=[True,True,False])
    with patch.object(Silver,"get_time",side_effect=[1,3]),patch("source.silver.map_sweep.time.sleep"):
        MapSweep.wait_simulation(2,control=control)
    assert control.call_count==3


def test_sweep_controls_use_same_api_owner_and_report_pause():
    import queue
    from source.setup_operation.setup_control_window import SetupControlWindow as Window
    commands=queue.Queue();responses=queue.Queue();stop=threading.Event()
    commands.put("clear_errors");commands.put("simulation_toggle")
    with patch.object(Op,"clear_errors") as clear,patch.object(Op,"set_paused",side_effect=lambda value:setattr(Op,"_requested_pause",value)) as pause,patch.object(Op,"_requested_pause",False):
        assert Window.sweep_control(commands,responses,"one.sil",stop)
        clear.assert_called_once_with(stop);pause.assert_called_once_with(True)
        assert responses.get_nowait()==("pause_state","one.sil",True)
        commands.put("simulation_toggle")
        assert not Window.sweep_control(commands,responses,"one.sil",stop)
        assert responses.get_nowait()==("pause_state","one.sil",False)


def test_torque_is_read_only_after_point_waits():
    events=[];log=[]
    settings={**SETTINGS,"rpm_to":1000,"pedal_to":.2}
    with patch.object(Op,"start_mode"),patch.object(Op,"write"),patch.object(Op,"set_inputs"),patch.object(MapSweep,"wait_simulation",side_effect=lambda *args:events.append("wait")),patch.object(Op,"read",side_effect=lambda name:(events.append(name) or 42)):
        MapSweep.run(settings,log.append)
    assert events==["wait","wait","HW__ICE__CrkShftTq_M"]
    assert log==["Drehzahl: 1000 rpm | Pedal: 0.2","Drehzahl: 1000 rpm | Pedal: 0.2 | HW__ICE__CrkShftTq_M: 42"]


def test_sweep_keeps_requested_controls_available():
    from PySide6.QtWidgets import QApplication
    from source.setup_operation.setup_control_window import SetupControlWindow as Window
    from source.core.config import Config
    app=QApplication.instance() or QApplication([])
    with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(Config,"set_state"):
        window=Window.open();state=window._setup_control
        try:
            state["selected"]=state["connected_path"]="one.sil"
            state["mode"].setCurrentText("Kennfeld-Rasterung")
            Window.run_operation(window,"sweep",SETTINGS)
            assert state["clear_errors"].isEnabled() and state["simulation"].isEnabled()
            Window.run_operation(window,"clear_errors")
            Window.run_operation(window,"simulation_toggle")
            assert list(state["sweep_commands"].queue)==["clear_errors","simulation_toggle"]
            assert state["pending_action"]=="sweep"
            Window.append_log(window,"Andere Aktion")
            assert state["log_view"].toPlainText()==""
        finally:window.close()
