import queue,threading
from unittest.mock import patch,call
import pytest
from source.silver.deferred_controls import SilverDeferredControls as Deferred
from source.silver.operation import SilverOperation as Op
from source.silver.methods import Silver
from source.silver.connection import SilverConnection as Connection
from source.setup_operation.setup_control_window import SetupControlWindow as Window

@pytest.fixture(autouse=True)
def reset():
    Deferred.reset();yield;Deferred.reset()


def test_paused_values_are_written_without_confirmation_or_engine_wait():
    with patch.object(Silver,"started_successfully",return_value=True),patch.object(Op,"read",return_value=0),patch.object(Op,"write") as write,patch.object(Op,"wait_above") as wait:
        assert set(Deferred.stage("ignition_engine"))=={"ignition","engine"}
        write.assert_any_call("mapping.mdl.pos_IgnitionSwitch_const",1)
        write.assert_any_call("mapping.mdl.pos_Starter_const",1)
        with patch.object(Op,"read",side_effect=AssertionError("No paused-state monitoring")):
            assert Deferred.tick(False)==["ignition","engine"]
        wait.assert_not_called()


def test_repeated_paused_toggles_use_pending_value_not_stale_readback():
    with patch.object(Silver,"started_successfully",return_value=True),patch.object(Op,"read",return_value=0),patch.object(Op,"write"):
        Deferred.stage("ignition");Deferred.stage("ignition")
        assert Deferred.values["mapping.mdl.pos_IgnitionSwitch_const"]==0
        Deferred.stage("start_stop");Deferred.stage("start_stop")
        assert Deferred.values["Parameters_SSA_Enbl_Rq_TCM"]==1


def test_unloaded_setup_queues_and_reapplies_when_running_then_releases_starter():
    with patch.object(Silver,"started_successfully",return_value=False),patch.object(Op,"read",return_value=0),patch.object(Op,"write") as write:
        Deferred.stage("ignition_engine");write.assert_not_called()
        Deferred.tick(True)
        write.assert_any_call("mapping.mdl.pos_IgnitionSwitch_const",1)
        write.assert_any_call("mapping.mdl.pos_Starter_const",1)
        with patch.object(Op,"read",side_effect=lambda name:500 if name=="n_EngineSpeed" else 1):
            assert Deferred.tick(True)==[]
        assert write.call_args_list[-1]==call("mapping.mdl.pos_Starter_const",0)


def test_error_reset_pulse_starts_counting_only_after_simulation_runs():
    with patch.object(Silver,"started_successfully",return_value=True),patch.object(Op,"write") as write,patch.object(Silver,"get_time",side_effect=[10,10.5,11.1]):
        Deferred.stage("clear_errors")
        Deferred.tick(False)
        assert not any(c.args[1]==0 for c in write.call_args_list)
        Deferred.tick(True)
        assert Deferred.tick(True)==["clear_errors"]
        assert Deferred.tick(True)==[]
        assert write.call_args_list[-2:]==[call("Master_DSMAUX_xClearTrg_C",0),call("Slave_DSMAUX_xClearTrg_C",0)]


def test_pause_disables_confirmation_deadline():
    with patch.object(Silver,"started_successfully",return_value=False),patch.object(Op,"write") as write:
        Deferred.stage("engine");Deferred.tick(True)
        Deferred.deadline=-1
        assert Deferred.tick(False)==["engine"]
        assert Deferred.deadline is None
        assert not any(c.args==("mapping.mdl.pos_Starter_const",0) for c in write.call_args_list)


def test_worker_reports_staged_action_instead_of_requesting_start_or_waiting():
    commands=queue.Queue();responses=queue.Queue()
    commands.put("setup.sil");commands.put(("operation","ignition_engine",None,"setup.sil"));commands.put(None)
    with patch.object(Connection,"connect",return_value={"reused":True}),patch.object(Connection,"disconnect"),patch.object(Connection,"alive",return_value=True),patch.object(Op,"simulation_running",return_value=False),patch.object(Silver,"started_successfully",return_value=True),patch.object(Op,"read",return_value=0),patch.object(Op,"write"),patch.object(Op,"ignition_and_motor_start") as blocking:
        Window.connection_loop(commands,responses,threading.Event(),threading.Event())
    kinds=[message[0] for message in list(responses.queue)]
    assert "deferred" in kinds and "pending_controls" in kinds
    assert "simulation_start_required" not in kinds
    blocking.assert_not_called()
