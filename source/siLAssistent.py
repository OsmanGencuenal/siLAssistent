"""siLAssistent entry point; importing APIs never starts INCA or Silver."""
import sys
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from source.core.config import Config
from source.core.runtime import Runtime

class Application:
    @classmethod
    def main(cls, argv=None):
        import argparse
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--version", action="store_true")
        parser.add_argument("--apply-update",help=argparse.SUPPRESS)
        parser.add_argument("--wait-for-pid",type=int,help=argparse.SUPPRESS)
        parser.add_argument("--wait-for-created",type=float,help=argparse.SUPPRESS)
        parser.add_argument("--export-user-config",help=argparse.SUPPRESS)
        parser.add_argument("--uninstall",help=argparse.SUPPRESS)
        parser.add_argument("--silver-api-worker",help=argparse.SUPPRESS)
        parser.add_argument("--silver-api-worker-test",help=argparse.SUPPRESS)
        parser.add_argument("--self-test", metavar="RESULT_JSON")
        parser.add_argument("--no-update", action="store_true")
        parser.add_argument("--sil-einrichten", action="store_true", help=argparse.SUPPRESS)
        parser.add_argument("--Assistent-Worker-result", "--silver-worker-result", dest="silver_worker_result", help=argparse.SUPPRESS)
        parser.add_argument("--silver-installer", help=argparse.SUPPRESS)
        parser.add_argument("--driver-path", help=argparse.SUPPRESS)
        parser.add_argument("--silver-update", action="store_true", help=argparse.SUPPRESS)
        parser.add_argument("--silver-target-version", help=argparse.SUPPRESS)
        parser.add_argument("--silver-previous-version", help=argparse.SUPPRESS)
        parser.add_argument("--silver-uninstall-target", help=argparse.SUPPRESS)
        args = parser.parse_args(argv)
        if args.apply_update:
            from source.core.update import UpdateManager
            try:
                if args.wait_for_pid is None or args.wait_for_created is None:raise ValueError("Update-Prozessangaben fehlen.")
                return UpdateManager.apply_after_exit(args.apply_update,args.wait_for_pid,args.wait_for_created)
            except Exception:
                Runtime.configure_logging().exception("Update installer could not be started")
                return 1
        if args.export_user_config or args.uninstall:
            from source.core.uninstall import Uninstall
            try:
                if args.export_user_config:Uninstall.export_user_config(args.export_user_config)
                else:Uninstall.start(args.uninstall)
                return 0
            except Exception as error:
                Runtime.configure_logging().exception("Uninstall/export action failed")
                if args.uninstall:
                    from PySide6.QtWidgets import QApplication
                    from source.ui.dialogs import Dialogs
                    app=QApplication.instance() or QApplication([])
                    Dialogs.message("Deinstallation konnte nicht gestartet werden",str(error))
                return 1
        if args.silver_api_worker or args.silver_api_worker_test:
            from source.silver.connection_worker import SilverConnectionWorker
            if args.silver_api_worker_test:return SilverConnectionWorker.self_test(args.silver_api_worker_test)
            SilverConnectionWorker.main(args.silver_api_worker)
            return 0
        if args.silver_worker_result:
            from source.silEinrichten import SilverInstallation
            SilverInstallation.configure_update(args.silver_update, args.silver_previous_version,
                                                args.silver_target_version, args.silver_uninstall_target)
            return SilverInstallation.helper_main(args.silver_worker_result,
                args.silver_installer or Config.STATE_DEFAULTS["silverInstallerPath"])
        if args.version:
            print(Config.version())
            return 0
        if args.self_test:
            from source.core.smoke import SmokeTest
            return SmokeTest.run(args.self_test)
        progress=None
        if not args.silver_update and not args.sil_einrichten:
            from PySide6.QtWidgets import QApplication
            from source.ui.progress import ProgressWindow
            app=QApplication.instance() or QApplication([])
            progress=ProgressWindow.create("startup")
            ProgressWindow.stage(progress,"Anwendung wird gestartet …",0,paint=True)
        Runtime.configure_logging()
        if progress is not None:ProgressWindow.stage(progress,"Konfiguration wird geladen …",25,paint=True)
        try:
            Config.ensure_state()
            if progress is not None:ProgressWindow.stage(progress,"Launcher wird vorbereitet …",50,paint=True)
        except Exception as error:
            if progress is not None:ProgressWindow.finish(progress)
            from PySide6.QtWidgets import QApplication
            from source.ui.dialogs import Dialogs
            app = QApplication.instance() or QApplication([])
            Dialogs.message("Konfiguration nicht schreibbar", f"Die INI-Datei im Installationspfad konnte nicht vorbereitet werden:\n{error}")
            return 1
        if args.silver_update:
            from source.silEinrichten import SilEinrichten
            return SilEinrichten.run_silver_update(args.silver_installer, args.silver_previous_version,
                                                   args.silver_target_version, args.silver_uninstall_target)
        if args.sil_einrichten:
            from source.silEinrichten import SilEinrichten
            return SilEinrichten.run(driver_path=args.driver_path, silver_installer=args.silver_installer)
        from source.ui.launcher import Launcher
        if progress is not None:ProgressWindow.stage(progress,"Oberfläche wird aufgebaut …",75,paint=True)
        return Launcher.run(check_updates=not args.no_update,progress=progress)

if __name__ == "__main__":
    import multiprocessing
    from source.core.process_runtime import ProcessRuntime
    ProcessRuntime.configure()
    multiprocessing.freeze_support()
    sys.exit(Application.main())
