import unittest
from unittest.mock import Mock,patch
from source.silver.connection_worker import SilverConnectionWorker as Worker

class SilverConnectionTests(unittest.TestCase):
    @classmethod
    def test_existing_setup_without_api_does_not_launch_duplicate(cls):
        remote=Mock()
        with patch.object(Worker,"remote",remote,create=True):
            with cls.assert_raises(RuntimeError):
                Worker.connect({"path":"existing.sil","existing":[{"ports":[],"pid":123}]})
            remote.RemoteSilver.assert_not_called()

    @classmethod
    def test_new_setup_starts_visible_and_stopped(cls):
        target=Mock();target.started_successfully.return_value=True;target._silver_process.pid=123
        remote=Mock();remote.RemoteSilver.return_value=target
        try:
            with patch.object(Worker,"remote",remote,create=True):
                result=Worker.connect({"path":"selected.sil","existing":[]})
                options=remote.RemoteSilver.call_args.kwargs
                assert options["gui"] and not options["stopped"]
                assert result["pid"]==123 and not result["reused"]
        finally:Worker.target=None

    @classmethod
    def assert_raises(cls,error):
        import pytest
        return pytest.raises(error)

    @classmethod
    def test_cancelled_rpc_aborts_start_without_waiting_for_timeout(cls):
        import threading,queue
        from source.silver.connection import SilverConnection,SilverStartCancelled
        event=threading.Event();event.set()
        process=Mock();process.poll.return_value=None
        with patch.object(SilverConnection,"_process",process),patch.object(SilverConnection,"_messages",queue.Queue()),patch.object(SilverConnection,"abort_start") as abort:
            with cls.assert_raises(SilverStartCancelled):SilverConnection.rpc("connect",cancelled=event)
            abort.assert_called_once()

    @classmethod
    def test_abort_only_targets_children_of_owned_helper(cls):
        import psutil
        from source.silver.connection import SilverConnection
        helper=Mock();helper.pid=111;helper.poll.return_value=None
        root=Mock();child=Mock();root.children.return_value=[child]
        with patch.object(SilverConnection,"_process",helper),patch.object(psutil,"Process",return_value=root) as lookup,patch.object(psutil,"wait_procs",return_value=([],[])):
            SilverConnection.abort_start()
            lookup.assert_called_once_with(111)
            root.suspend.assert_called_once();child.kill.assert_called_once();root.kill.assert_called_once()

    @classmethod
    def test_auto_does_not_launch_or_disconnect_when_setup_closed(cls):
        import tempfile
        from pathlib import Path
        from source.silver.connection import SilverConnection
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"test.sil";path.write_text("")
            with patch.object(SilverConnection,"running_setups",return_value=[]),patch.object(SilverConnection,"disconnect") as disconnect,patch("source.silver.connection.subprocess.Popen") as launch:
                assert SilverConnection.connect(path,allow_start=False) is None
                launch.assert_not_called();disconnect.assert_not_called()

    @classmethod
    def test_disconnect_closes_only_helper_not_silver(cls):
        from source.silver.connection import SilverConnection
        from source.silver.api import Silver
        process=Mock();process.poll.return_value=None
        with patch.object(SilverConnection,"_process",process),patch.object(Silver,"_sessions",{}),patch.object(SilverConnection,"abort_start") as abort,patch.object(SilverConnection,"rpc",return_value=True):
            SilverConnection.disconnect()
            assert 'disconnect' in process.stdin.write.call_args.args[0]
            process.wait.assert_called_once_with(timeout=2)
            abort.assert_not_called()

    @classmethod
    def test_disconnect_releases_all_owned_overrides(cls):
        target=Mock();target.get_variable_names.return_value=[];target.get_parameter_names.return_value=[]
        with patch.object(Worker,"target",target),patch.object(Worker,"overrides",set()):
            Worker.dispatch({"op":"call","method":"set_variable_value","args":["mapping.mdl.pos_AcceleratorPedal_const",0.2]})
            Worker.dispatch({"op":"call","method":"set_variable_value","args":["mapping.mdl.n_EngineSpeed_const",750]})
            Worker.dispatch({"op":"release"})
            assert not Worker.overrides
            target.set_variable_value.assert_any_call("mapping.mdl.pos_AcceleratorPedal_const",None)
            target.set_variable_value.assert_any_call("mapping.mdl.n_EngineSpeed_const",None)
            target.exit.assert_not_called()

    @classmethod
    def test_release_failure_does_not_skip_other_variables(cls):
        def setter(name,value):
            if name=="bad":raise RuntimeError("failed")
        target=Mock();target.set_variable_value.side_effect=setter
        with patch.object(Worker,"target",target),patch.object(Worker,"overrides",{"bad","ok"}):
            with cls.assert_raises(RuntimeError):Worker.release_overrides()
            assert Worker.overrides=={"bad"}
            target.set_variable_value.assert_any_call("ok",None)

    @classmethod
    def test_cleanup_waits_longer_than_normal_api_reads(cls):
        from source.silver.connection import SilverConnection as C
        with patch.object(C,"rpc",return_value=True) as rpc:
            C.call("stop")
            assert rpc.call_args.kwargs["timeout"]==300
            C.call("get_time")
            assert rpc.call_args.kwargs["timeout"]==10


class ExistingApiRecoveryTests(unittest.TestCase):
    @classmethod
    def test_late_listener_is_refreshed_and_rpc_verified(cls):
        api=Mock();grpc=Mock();library=Mock();library.SilverApi.return_value=api
        candidate={'pid':123,'ports':[],'api_expected':True}
        with patch.object(Worker,'grpc_api',library,create=True),patch.object(Worker,'grpc',grpc,create=True),patch.object(Worker,'existing_ports',side_effect=[[],[54321]]),patch('source.silver.connection_worker.time.sleep'),patch.object(Worker,'target',None),patch.object(Worker,'remote',Mock()) as remote:
            result=Worker.connect({'path':'selected.sil','existing':[candidate]})
            assert result['reused'] and result['pid']==123
            api._simulation_control.StartedSuccessfully.assert_called_once_with(library.Empty.return_value,timeout=2)
            remote.RemoteSilver.assert_not_called()

    @classmethod
    def test_http2_listener_is_not_enough_and_channel_is_closed(cls):
        api=Mock();api._simulation_control.StartedSuccessfully.side_effect=RuntimeError('Unimplemented service')
        library=Mock();library.SilverApi.return_value=api
        with patch.object(Worker,'grpc_api',library,create=True),patch.object(Worker,'grpc',Mock(),create=True),patch.object(Worker,'existing_ports',return_value=[21845]),patch.object(Worker,'target',None),patch.object(Worker,'remote',Mock()) as remote:
            with unittest.TestCase().assertRaisesRegex(RuntimeError,'ohne aktivierte Remote-API'):
                Worker.connect({'path':'selected.sil','existing':[{'pid':123,'api_expected':False}]})
            api.channel.close.assert_called_once();assert Worker.target is None
            remote.RemoteSilver.assert_not_called()

    @classmethod
    def test_reused_pid_is_rejected_before_reading_ports(cls):
        process=Mock();process.create_time.return_value=200
        with patch('psutil.Process',return_value=process):
            with unittest.TestCase().assertRaisesRegex(RuntimeError,'ersetzt'):
                Worker.existing_ports({'pid':123,'created':100})
            process.net_connections.assert_not_called()

    @classmethod
    def test_api_start_retry_is_bounded(cls):
        with patch.object(Worker,'existing_ports',return_value=[]),patch('source.silver.connection_worker.time.monotonic',side_effect=[0,31]),patch.object(Worker,'remote',Mock()) as remote:
            with unittest.TestCase().assertRaisesRegex(RuntimeError,'erneuter Prüfung'):
                Worker.connect({'path':'selected.sil','existing':[{'pid':123,'api_expected':True}]})
            remote.RemoteSilver.assert_not_called()
