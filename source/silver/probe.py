"""Spawn-safe Silver discovery: persist local version before any network operation."""
import multiprocessing
import os
import time
from ..core.process_runtime import ProcessRuntime
from .updates import SilverUpdates


class SilverProbe:
    @classmethod
    def run(cls, connection, update_ini_path, state_ini_path=None):
        try:
            version = SilverUpdates.refresh_local_version(state_ini_path)
            connection.send(("silver_local", {"version": version, "pid": os.getpid()}))
            if update_ini_path:
                connection.send(("silver_release", SilverUpdates.check(update_ini_path)))
        except Exception as error:
            connection.send(("check_error", "Silver: " + str(error)))
        finally:
            connection.close()

    @classmethod
    def collect(cls, update_ini_path, destination, state_ini_path=None, timeout=120):
        ProcessRuntime.configure()
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=cls.run, args=(sender, update_ini_path, state_ini_path), daemon=True)
        try:
            process.start()
            sender.close()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    if receiver.poll(0.2):
                        destination.put(receiver.recv())
                    elif not process.is_alive():
                        break
                except (EOFError, BrokenPipeError):
                    break
            else:
                destination.put(("check_error", "Silver: Zeitüberschreitung bei der Hintergrundprüfung."))
        finally:
            if process.pid is not None:
                process.join(timeout=5)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
                if process.exitcode not in (0, None):
                    destination.put(("check_error", "Silver-Hintergrundprozess wurde vorzeitig beendet."))
                process.close()
            receiver.close()
            sender.close()
