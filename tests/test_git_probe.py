import os
import multiprocessing
import unittest
from unittest.mock import Mock,patch
from source.core.git_probe import GitProbe
from source.core.process_runtime import ProcessRuntime
from source.stand_management.git_installation import GitInstallation
from source.core.config import Config

class GitProbeTests(unittest.TestCase):
    @classmethod
    def test_real_spawn_runs_in_different_process(cls):
        context=multiprocessing.get_context("spawn")
        receiver,sender=context.Pipe(duplex=False)
        process=context.Process(target=GitProbe.run,args=(sender,))
        try:
            process.start()
            sender.close()
            assert receiver.poll(20),"No result from child process"
            result=receiver.recv()
            assert result["pid"]!=os.getpid()
            assert result["pid"]==process.pid
            assert result["error"] is None
            process.join(timeout=5)
            assert process.exitcode==0
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            receiver.close()
            sender.close()
            process.close()

    @classmethod
    def test_compiled_spawn_uses_executable_protocol(cls):
        import sys
        command=ProcessRuntime.compiled_command_line(parent_pid=123,pipe_handle=456)
        assert command[:2]==[sys.executable,"--multiprocessing-fork"]
        assert "-c" not in command

    @classmethod
    def test_result_sets_state_and_resumes_action(cls):
        import time
        window=Mock()
        process=Mock()
        process.is_alive.return_value=False
        receiver=Mock()
        receiver.poll.return_value=True
        receiver.recv.return_value={"path":"git.exe","error":None}
        retry=Mock()
        window._git_probe={"process":process,"receiver":receiver,"timer":Mock(),"result":None,"started":time.monotonic(),"retry":retry,"notify":True}
        with patch.object(Config,"set_state") as save,patch.object(GitInstallation,"_resolved_executable",None,create=True):
            GitInstallation.poll_probe(window)
            save.assert_called_once_with("GitInstallationState",True)
            retry.assert_called_once()
            assert window._git_probe is None
            process.join.assert_called_once_with(timeout=0)
