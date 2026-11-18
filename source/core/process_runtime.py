"""Windows spawn configuration shared by source and Nuitka builds."""
import os
import sys
import multiprocessing.spawn as spawn

class ProcessRuntime:
    @classmethod
    def compiled_command_line(cls, **kwargs):
        return [sys.executable,"--multiprocessing-fork",*(f"{name}={value!r}" for name,value in kwargs.items())]

    @classmethod
    def configure(cls):
        if os.name=="nt" and ("__compiled__" in globals() or getattr(sys,"frozen",False)):
            spawn.get_command_line=cls.compiled_command_line

    @classmethod
    def self_test(cls):
        import multiprocessing
        from .git_probe import GitProbe
        cls.configure()
        context=multiprocessing.get_context("spawn")
        receiver,sender=context.Pipe(duplex=False)
        process=context.Process(target=GitProbe.run,args=(sender,),daemon=True)
        try:
            process.start()
            sender.close()
            if not receiver.poll(20):
                raise RuntimeError("Multiprocessing self-test timed out")
            result=receiver.recv()
            process.join(timeout=5)
            if result.get("pid")==os.getpid() or process.exitcode!=0:
                raise RuntimeError("Multiprocessing self-test failed")
            return True
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            receiver.close()
            sender.close()
            process.close()
