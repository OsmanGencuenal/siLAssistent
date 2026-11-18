import unittest
from unittest.mock import patch,call
from source.silver.operation import SilverOperation as Op
from source.silver.methods import Silver

class SilverOperationTests(unittest.TestCase):
    @classmethod
    def test_engine_start_and_starter_cleanup(cls):
        values={Op.PREFIX+"pos_IgnitionSwitch_const":0,"n_EngineSpeed":0}
        writes=[]
        def write(name,value):
            writes.append((name,value));values[name]=value
            if name.endswith("pos_Starter_const") and value==1:values["n_EngineSpeed"]=500
        with patch.object(Op,"read",side_effect=lambda n:values[n]),patch.object(Op,"write",side_effect=write):
            assert Op.startEngine()
        assert writes==[(Op.PREFIX+"pos_IgnitionSwitch_const",1),(Op.PREFIX+"pos_Starter_const",1),(Op.PREFIX+"pos_Starter_const",0)]

    @classmethod
    def test_starter_cleared_on_failure(cls):
        import pytest
        with patch.object(Op,"ignition"),patch.object(Op,"read",return_value=0),patch.object(Op,"write") as write,patch.object(Op,"wait_above",side_effect=RuntimeError("timeout")):
            with pytest.raises(RuntimeError):Op.startEngine()
            assert write.call_args_list[-1]==call(Op.PREFIX+"pos_Starter_const",0)

    @classmethod
    def test_gears_brake_before_selector(cls):
        for gear,value in {"R":-1,"N":0,"D":5,"P":-2}.items():
            events=[]
            with patch.object(Op,"write",side_effect=lambda n,v:events.append((n,v))),patch.object(Op,"wait_above",side_effect=lambda *a:events.append("brake-confirmed")):
                Op.switchGear(gear)
            assert events==[(Op.PREFIX+"pos_BrakePedal_const",100),"brake-confirmed",(Op.PREFIX+"pos_Selector_const",value)]

    @classmethod
    def test_testbench_sequence(cls):
        with patch.object(Op,"read",return_value=0),patch.object(Op,"simulation_running",return_value=True),patch.object(Silver,"started_successfully",return_value=True),patch.object(Silver,"run"),patch.object(Op,"startEngine",return_value=True),patch.object(Op,"switchGear") as gear,patch.object(Op,"wait_above"),patch.object(Op,"write") as write:
            Op.start_mode("Test-Bench")
            gear.assert_called_once_with("D",None)
            assert write.call_args_list==[call(Op.PREFIX+"pos_IgnitionSwitch_mode",0),call(Op.PREFIX+"pos_AcceleratorPedal_mode",0),call(Op.PREFIX+"pos_BrakePedal_mode",0),call(Op.PREFIX+"pos_Selector_mode",0),call(Op.PREFIX+"n_EngineSpeed_const",750),call(Op.PREFIX+"n_EngineSpeed_mode",0),call(Op.PREFIX+"pos_BrakePedal_const",0)]

    @classmethod
    def test_imo_and_cycle_values(cls):
        with patch.object(Op,"simulation_running",return_value=True),patch.object(Silver,"started_successfully",return_value=True),patch.object(Silver,"run") as run,patch.object(Op,"write") as write:
            with patch.object(Op,"initialize_imo"):
                Op.start_mode("IMO")
            assert write.call_count==7
            assert call("Parameters.v_TargetSpeed_mode_GUI",0) in write.call_args_list
            assert call(Op.PREFIX+"n_EngineSpeed_mode",2) in write.call_args_list
            assert call(Op.PREFIX+"pos_GearShift_mode",2) in write.call_args_list
            write.reset_mock();Op.start_mode("Zyklus")
            write.assert_called_once_with("Parameters.v_TargetSpeed_mode_GUI",100)
            assert run.call_count==2

    @classmethod
    def test_ignition_toggles_both_directions(cls):
        for value,target in ((1,0),(0,1)):
            with patch.object(Op,"read",return_value=value),patch.object(Op,"write") as write:
                Op.toggle_ignition()
                write.assert_called_once_with(Op.PREFIX+"pos_IgnitionSwitch_const",target)

    @classmethod
    def test_motor_button_uses_requested_const_and_cleans_starter(cls):
        with patch.object(Op,"read",side_effect=lambda name:1 if "IgnitionSwitch" in name else 0),patch.object(Op,"wait_above") as wait,patch.object(Op,"write") as write:
            Op.motor_start()
            wait.assert_called_once_with("n_EngineSpeed",300,None)
            assert write.call_args_list==[call(Op.PREFIX+"pos_Starter_const",1),call(Op.PREFIX+"pos_Starter_const",0)]

    @classmethod
    def test_motor_with_ignition_off_never_sets_starter(cls):
        import pytest
        with patch.object(Op,"read",return_value=0),patch.object(Op,"write") as write:
            with pytest.raises(RuntimeError,match="Zündung ist nicht AN"):
                Op.motor_start()
            write.assert_not_called()

    @classmethod
    def test_running_requires_advancing_simulation_time(cls):
        with patch.object(Silver,"started_successfully",return_value=True),patch.object(Silver,"get_time",side_effect=[0,0.1]),patch("source.silver.operation.time.sleep"):
            assert Op.simulation_running()
        with patch.object(Silver,"started_successfully",return_value=True),patch.object(Op,"_requested_pause",None),patch.object(Silver,"get_time",return_value=0),patch("source.silver.operation.time.monotonic",side_effect=[0,0,2]),patch("source.silver.operation.time.sleep"):
            assert Op.simulation_running() is None

    @classmethod
    def test_engine_status_uses_actual_speed(cls):
        with patch.object(Op,"read",side_effect=lambda name:450 if name=="n_EngineSpeed" else 1) as read:
            assert Op.states()=={"ignition":True,"engine":True,"start_stop":False}
            assert call("n_EngineSpeed") in read.call_args_list
            assert call(Op.PREFIX+"n_EngineSpeed_const") not in read.call_args_list

    @classmethod
    def test_stopped_setup_reloads_before_imo_writes(cls):
        events=[]
        with patch.object(Op,"simulation_running",return_value=False),patch.object(Silver,"started_successfully",side_effect=[False,True]),patch.object(Silver,"reload",side_effect=lambda **kw:events.append("reload")),patch.object(Silver,"run",side_effect=lambda **kw:events.append("run")),patch.object(Op,"write",side_effect=lambda *args:events.append(args)):
            with patch.object(Op,"initialize_imo"):
                Op.start_mode("IMO")
        assert events[:2]==["reload","run"]
        assert events[2]==("Parameters.v_TargetSpeed_mode_GUI",0)

    @classmethod
    def test_load_failure_prevents_mode_writes(cls):
        import pytest
        with patch.object(Silver,"started_successfully",return_value=False),patch.object(Silver,"reload",side_effect=RuntimeError("crash")),patch.object(Op,"write") as write:
            with pytest.raises(RuntimeError,match="Setup ist nicht erfolgreich geladen"):
                with patch.object(Op,"initialize_imo"):
                    Op.start_mode("IMO")
            write.assert_not_called()

    @classmethod
    def test_reload_waits_until_ready_before_settings(cls):
        events=[]
        with patch.object(Silver,"started_successfully",side_effect=[False,False,True]),patch.object(Silver,"reload"),patch.object(Silver,"run"),patch("source.silver.operation.time.sleep") as sleep,patch.object(Op,"write") as write:
            with patch.object(Op,"initialize_imo"):
                Op.start_mode("IMO")
            sleep.assert_called_once_with(0.2)
            assert write.call_count==7

    @classmethod
    def test_testbench_releases_manual_engine_overrides_even_on_error(cls):
        import pytest
        writes=[]
        def write(name,value):
            writes.append((name,value))
            if name.endswith("n_EngineSpeed_mode") and value==0:raise RuntimeError("failure")
        with patch.object(Op,"read",return_value=0),patch.object(Op,"simulation_running",return_value=True),patch.object(Silver,"started_successfully",return_value=True),patch.object(Silver,"run"),patch.object(Op,"startEngine",return_value=True),patch.object(Op,"switchGear"),patch.object(Op,"wait_above"),patch.object(Op,"write",side_effect=write):
            with pytest.raises(RuntimeError):Op.start_mode("Test-Bench")
        assert writes[-2:]==[(Op.PREFIX+"n_EngineSpeed_const",None),(Op.PREFIX+"n_EngineSpeed_mode",None)]

    @classmethod
    def test_manual_inputs_and_cycle_mappings(cls):
        with patch.object(Op,"write") as write:
            Op.set_input("rpm","1500");Op.set_input("accelerator","0,5");Op.set_input("brake",1)
            assert write.call_args_list==[call(Op.PREFIX+"n_EngineSpeed_const",1500),call(Op.PREFIX+"pos_AcceleratorPedal_const",0.5),call(Op.PREFIX+"pos_BrakePedal_const",1)]
            write.reset_mock()
            for cycle in ("NEDC","FTP75","US06","WLTP"):Op.set_cycle(cycle)
            assert write.call_args_list==[call("DriveCycleIdxGui",13),call("DriveCycleIdxGui",5),call("DriveCycleIdxGui",10),call("DriveCycleIdxGui",8)]

    @classmethod
    def test_invalid_manual_input_does_not_write(cls):
        import pytest
        with patch.object(Op,"write") as write:
            for key,value in (("rpm","abc"),("rpm",-1),("accelerator",101),("brake","nan")):
                with pytest.raises(ValueError):Op.set_input(key,value)
            write.assert_not_called()

    @classmethod
    def test_cycle_selected_after_reload_before_run(cls):
        events=[]
        with patch.object(Silver,"started_successfully",side_effect=[False,True]),patch.object(Op,"simulation_running",return_value=False),patch.object(Silver,"reload",side_effect=lambda **kw:events.append("reload")),patch.object(Silver,"run",side_effect=lambda **kw:events.append("run")),patch.object(Op,"write",side_effect=lambda n,v:events.append((n,v))):
            Op.start_mode("Zyklus",cycle="WLTP")
        assert events[:3]==["reload",("DriveCycleIdxGui",8),"run"]

    @classmethod
    def test_pause_and_resume_use_public_api(cls):
        with patch.object(Silver,"pause") as pause,patch.object(Silver,"run") as run:
            Op.set_paused(True)
            pause.assert_called_once_with(session=Op.SESSION);run.assert_not_called()
            Op.set_paused(False)
            run.assert_called_once_with(session=Op.SESSION)

    @classmethod
    def test_loaded_paused_setup_starts_without_reloading(cls):
        with patch.object(Silver,"started_successfully",return_value=True),patch.object(Silver,"reload") as reload,patch.object(Silver,"run") as run,patch.object(Op,"simulation_running",side_effect=AssertionError("Readiness must not be inferred from time")),patch.object(Op,"write") as write:
            with patch.object(Op,"initialize_imo"):
                Op.start_mode("IMO")
            reload.assert_not_called()
            run.assert_called_once_with(session=Op.SESSION)
            assert write.call_count==7

    @classmethod
    def test_combined_start_confirms_ignition_before_motor(cls):
        events=[]
        with patch.object(Op,"ignition",side_effect=lambda event:events.append("ignition-confirmed")),patch.object(Op,"motor_start",side_effect=lambda event:events.append("motor")):
            Op.ignition_and_motor_start()
        assert events==["ignition-confirmed","motor"]
        import pytest
        with patch.object(Op,"ignition",side_effect=RuntimeError("Zündung fehlt")),patch.object(Op,"motor_start") as motor:
            with pytest.raises(RuntimeError):Op.ignition_and_motor_start()
            motor.assert_not_called()

    @classmethod
    def test_testbench_configures_rpm_before_start_and_drive(cls):
        events=[]
        with patch.object(Op,"read",return_value=0),patch.object(Silver,"started_successfully",return_value=True),patch.object(Silver,"run"),patch.object(Op,"write",side_effect=lambda n,v:events.append((n,v))),patch.object(Op,"startEngine",side_effect=lambda e:(events.append("engine-confirmed") or True)),patch.object(Op,"switchGear",side_effect=lambda *a:events.append("drive")),patch.object(Op,"wait_above"):
            Op.start_mode("Test-Bench")
        assert events.index((Op.PREFIX+"n_EngineSpeed_mode",0))<events.index("engine-confirmed")<events.index("drive")
        assert events[-1]==(Op.PREFIX+"pos_BrakePedal_const",0)

    @classmethod
    def test_start_stop_toggles_between_one_and_two(cls):
        for current,target in ((1,2),(2,1)):
            with patch.object(Op,"read",return_value=current),patch.object(Op,"write") as write:
                Op.toggle_start_stop()
                write.assert_called_once_with("Parameters_SSA_Enbl_Rq_TCM",target)

    @classmethod
    def test_imo_parks_without_changing_ssa_or_ignition(cls):
        values={"Parameters_SSA_Enbl_Rq_TCM":2,Op.PREFIX+"pos_IgnitionSwitch_const":0,Op.PREFIX+"pos_Selector_const":-1,Op.PREFIX+"pos_BrakePedal_const":0}
        def write(name,value):values[name]=value
        with patch.object(Op,"write",side_effect=write) as writes,patch.object(Op,"read",side_effect=lambda name:values[name]),patch.object(Op,"startEngine") as engine:
            Op.initialize_imo()
        assert values["Parameters_SSA_Enbl_Rq_TCM"]==2
        assert values[Op.PREFIX+"pos_IgnitionSwitch_const"]==0
        assert values[Op.PREFIX+"pos_Selector_const"]==-2
        assert values[Op.PREFIX+"pos_BrakePedal_const"]==100
        engine.assert_not_called()

    @classmethod
    def test_batch_validates_every_value_before_writing(cls):
        import pytest
        with patch.object(Op,"write") as write:
            with pytest.raises(ValueError):Op.set_inputs({"accelerator":"0.2","brake":"101"})
            write.assert_not_called()
            Op.set_inputs({"accelerator":"0.2","brake":"0.5"})
            assert write.call_args_list==[call(Op.PREFIX+"pos_AcceleratorPedal_const",0.2),call(Op.PREFIX+"pos_BrakePedal_const",0.5)]

    @classmethod
    def test_motor_speed_timeout_uses_user_message(cls):
        import pytest
        with patch.object(Op,"read",return_value=0),patch("source.silver.operation.time.monotonic",side_effect=[0,31]):
            with pytest.raises(RuntimeError,match="^Motor ist nicht gestartet[.]$"):
                Op.wait_above("n_EngineSpeed",300)

    @classmethod
    def test_explicit_reload_does_not_reopen_configuration(cls):
        with patch.object(Silver,"reload") as reload,patch.object(Silver,"open") as open,patch.object(Silver,"started_successfully",return_value=True):
            Op.reload_setup()
            reload.assert_called_once_with(session=Op.SESSION)
            open.assert_not_called()

    @classmethod
    def test_ignition_off_never_requires_simulation_start(cls):
        with patch.object(Op,"read",return_value=1):
            assert not Op.needs_simulation_start_check("ignition")
        with patch.object(Op,"read",return_value=0):
            assert Op.needs_simulation_start_check("ignition")

    @classmethod
    def test_confirmed_unloaded_setup_requires_start(cls):
        with patch.object(Silver,"started_successfully",return_value=False),patch.object(Silver,"get_time") as get_time:
            assert Op.simulation_running() is False
            get_time.assert_not_called()

    @classmethod
    def test_testbench_preserves_current_running_rpm(cls):
        with patch.object(Op,"read",return_value=2000),patch.object(Silver,"started_successfully",return_value=True),patch.object(Silver,"run"),patch.object(Op,"startEngine",return_value=True),patch.object(Op,"switchGear"),patch.object(Op,"wait_above"),patch.object(Op,"write") as write:
            Op.start_mode("Test-Bench")
            assert call(Op.PREFIX+"n_EngineSpeed_const",2000) in write.call_args_list
            assert call(Op.PREFIX+"n_EngineSpeed_const",750) not in write.call_args_list

    @classmethod
    def test_clear_errors_pulses_both_signals_then_resets(cls):
        events=[]
        with patch.object(Op,"write",side_effect=lambda name,value:events.append((name,value))),patch("source.silver.operation.time.sleep",side_effect=lambda seconds:events.append(("wait",seconds))):
            Op.clear_errors()
        assert events==[("Master_DSMAUX_xClearTrg_C",255),("Slave_DSMAUX_xClearTrg_C",255),("wait",1.0),("Master_DSMAUX_xClearTrg_C",0),("Slave_DSMAUX_xClearTrg_C",0)]

    @classmethod
    def test_clear_errors_resets_both_on_write_failure(cls):
        import pytest
        events=[]
        def write(name,value):
            events.append((name,value))
            if name=="Slave_DSMAUX_xClearTrg_C" and value==255:raise RuntimeError("failed")
        with patch.object(Op,"write",side_effect=write):
            with pytest.raises(RuntimeError):Op.clear_errors()
        assert events[-2:]==[("Master_DSMAUX_xClearTrg_C",0),("Slave_DSMAUX_xClearTrg_C",0)]

    @classmethod
    def test_successful_api_writes_are_logged_with_meaningful_values(cls):
        import queue
        messages=queue.Queue()
        with patch.object(Op,"_log_messages",messages),patch.object(Silver,"set_variable_value",return_value=None):
            Op.write(Op.PREFIX+"pos_IgnitionSwitch_const",1)
            Op.write(Op.PREFIX+"n_EngineSpeed_const",2000)
            Op.write(Op.PREFIX+"pos_AcceleratorPedal_const",.2)
            Op.write(Op.PREFIX+"n_EngineSpeed_mode",0)
            Op.write(Op.PREFIX+"pos_Selector_const",5)
        texts=[item[2] for item in list(messages.queue)]
        assert texts==["Klemme 15: AN","Drehzahlvorgabe: 2000 rpm","Gas-Pedal: 20 %","Drehzahl-Modus: Manuell (0)","Gang: D"]

    @classmethod
    def test_background_status_sampling_is_one_read_and_never_sleeps(cls):
        with patch.object(Op,"_last_sim_time",None),patch.object(Op,"_last_sim_change",None),patch.object(Op,"_requested_pause",None),patch.object(Silver,"get_time",side_effect=[1,2]),patch("source.silver.operation.time.sleep") as sleep:
            assert Op.sample_simulation_state() is None
            assert Op.sample_simulation_state() is True
            sleep.assert_not_called()


def test_pause_acknowledgement_resets_old_time_baseline():
    from source.silver.operation import SilverOperation as Op
    from source.silver.methods import Silver
    with patch.object(Op,"_last_sim_time",100),patch.object(Op,"_last_sim_change",0),patch.object(Op,"_requested_pause",False),patch.object(Silver,"pause",return_value=True),patch.object(Silver,"get_time",side_effect=[101,101]):
        Op.set_paused(True)
        assert Op.sample_simulation_state() is False
        assert Op.sample_simulation_state() is False


def test_stalled_sample_does_not_override_confirmed_run():
    from source.silver.operation import SilverOperation as Op
    from source.silver.methods import Silver
    with patch.object(Op,"_last_sim_time",100),patch.object(Op,"_last_sim_change",0),patch.object(Op,"_requested_pause",False),patch.object(Silver,"get_time",return_value=100),patch("source.silver.operation.time.monotonic",return_value=10):
        assert Op.sample_simulation_state() is None
