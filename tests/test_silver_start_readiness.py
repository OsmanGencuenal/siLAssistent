from unittest.mock import Mock,patch
import io,queue
import pytest
from source.silver.connection_worker import SilverConnectionWorker as Worker
from source.silver.connection import SilverConnection
from source.core.runtime import Runtime


def test_cold_start_waits_for_same_instance_instead_of_failing_or_restarting():
    target=Mock();target.started_successfully.side_effect=[False,False,True]
    target._silver_process.poll.return_value=None
    remote=Mock();remote.RemoteSilver.return_value=target
    with patch.object(Worker,"remote",remote),patch("source.silver.connection_worker.time.sleep") as sleep,patch.object(Worker,"diagnostic"):
        try:
            result=Worker.connect({"path":"setup.sil","existing":[],"gui":True})
            assert target.started_successfully.call_count==3
            assert sleep.call_count==2
            remote.RemoteSilver.assert_called_once()
            target.exit.assert_not_called()
            assert result["pid"]==target._silver_process.pid
        finally:Worker.target=None


def test_process_exit_ends_readiness_wait_without_retry():
    target=Mock();target.started_successfully.return_value=False
    target._silver_process.poll.return_value=1;target._silver_process.returncode=1
    with patch.object(Worker,"diagnostic"),patch("source.silver.connection_worker.time.sleep") as sleep:
        with pytest.raises(RuntimeError,match="Exitcode 1"):Worker.wait_for_ready(target)
        sleep.assert_not_called()


def test_readiness_timeout_leaves_process_open_and_never_reloads():
    target=Mock();target.started_successfully.return_value=False;target._silver_process.poll.return_value=None
    with patch.object(Worker,"diagnostic"),patch.object(Worker,"READY_TIMEOUT",0):
        with pytest.raises(RuntimeError,match="keine zweite Instanz"):Worker.wait_for_ready(target)
    target.exit.assert_not_called();target.reload.assert_not_called();target._silver_process.terminate.assert_not_called()


def test_vendor_start_messages_are_retained(tmp_path):
    messages=queue.Queue()
    with patch.object(Runtime,"data_root",return_value=tmp_path):
        SilverConnection.read_output(io.StringIO('Timeout waiting for Silver\nSILASSISTENT_RPC {"id":"1","result":true}\n'),messages)
    assert 'Timeout waiting for Silver' in (tmp_path/'Logs'/'silver_connection_worker.log').read_text()
    assert messages.get()["result"] is True


def test_temporary_api_unavailability_during_loading_does_not_abort():
    target=Mock();target.started_successfully.side_effect=[ConnectionError("not ready"),False,True]
    target._silver_process.poll.return_value=None
    with patch.object(Worker,"diagnostic"),patch("source.silver.connection_worker.time.sleep"):
        Worker.wait_for_ready(target)
    assert target.started_successfully.call_count==3
    target.exit.assert_not_called()
