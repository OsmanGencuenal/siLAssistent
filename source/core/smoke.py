"""Isolated source/compiled smoke check; no vendor application or network required."""
from pathlib import Path
import json
import inspect
import hashlib
from unittest.mock import Mock
from .catalog import Catalog
from .config import Config

class SmokeTest:
    @classmethod
    def run(cls, destination):
        from ..inca import Inca, IncaMethods
        from ..silver import Silver
        inca_names = sorted({x["name"] for x in Catalog.load("inca")["methods"]})
        target = Mock()
        Inca.connect("smoke", application=target)
        try:
            for name in inca_names:
                getattr(target, name).return_value = name
                result = getattr(IncaMethods, name)(target, "argument", session="smoke")
                if result != name:
                    raise AssertionError(name)
        finally:
            Inca.disconnect("smoke")
        silver_names = sorted({x["name"] for x in Catalog.load("silver")["methods"]})
        for name in silver_names:
            backend = Mock()
            getattr(backend, name).return_value = name
            Silver.attach(backend, session="smoke")
            member = getattr(Silver, name)
            args = ["argument" for param in list(inspect.signature(member).parameters.values())
                    if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
                    and param.default is param.empty]
            member(*args, session="smoke")
            getattr(backend, name).assert_called_once()
            if "smoke" in Silver._sessions:
                Silver.release("smoke")
        from PySide6.QtWidgets import QApplication, QToolButton, QPushButton, QTabWidget
        from ..ui.launcher import Launcher
        app = QApplication.instance() or QApplication([])
        window = Launcher.create()
        window.show()
        app.processEvents()
        left = window.findChild(QToolButton, "standHeader")
        right = window.findChild(QToolButton, "operationHeader")
        if left is None or right is None or left.text() != "Stand-Management" or right.text() != "Setup-Betrieb":
            raise AssertionError("Launcher sections missing")
        if window.findChildren(QTabWidget):
            raise AssertionError("Backend API tabs leaked into launcher")
        setup = window.findChild(QPushButton, "setupButton")
        if setup is None or setup.text() != "SiL-Einrichten":
            raise AssertionError("Setup action missing")
        if window.windowIcon().isNull():
            raise AssertionError("Assistant icon missing")
        left.click()
        right.click()
        app.processEvents()
        if not left.isChecked() or not right.isChecked():
            raise AssertionError("Launcher sections are not interactive")
        if window.findChild(QPushButton, "gitTool") is None or window.findChild(QPushButton, "jiraTool") is None:
            raise AssertionError("Stand-management tools missing")
        from ..silEinrichten import SilEinrichten, SilverInstallation
        from ..core.config import Config
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "siLAssistent.ini"
            Config.ensure_state(state_path)
            if (dict(Config.parser(state_path)["STATE"]) | dict(Config.parser(state_path)["USER"]) | dict(Config.parser(state_path)["PATH"])) != Config.STATE_DEFAULTS:
                raise AssertionError("First-install defaults differ")
        if SilverInstallation.INSTALLER_PATH != Config.STATE_DEFAULTS["silverInstallerPath"]:
            raise AssertionError("Setup default path differs from state configuration")
        dialog, footer, body = SilEinrichten.create_card("SiL-Einrichten", "Test")
        if dialog.windowIcon().isNull():
            raise AssertionError("Setup dialog icon missing")
        dialog.close()
        window.close()
        from .process_runtime import ProcessRuntime
        multiprocessing_ok=ProcessRuntime.self_test()
        from ..silver.licences import SilverLicences
        portable=cls.portable_runtime_check()
        portable["silver_api_worker"]=cls.api_worker_self_test() if portable["packaged"] else False
        portable["offline_drivers"]=cls.offline_driver_check() if portable["packaged"] else False
        report = {**portable,"release_paths":{key:Config.STATE_DEFAULTS[key] for key in ("silverInstallerPath","silSetupPath","GitInstallationPath","GitSetupRepo")},"silver_license_servers":list(SilverLicences.servers()),"multiprocessing":multiprocessing_ok,"ok": True, "version": Config.version(), "inca_methods": len(inca_names),
                  "silver_methods": len(silver_names), "launcher_ui": True, "setup_ui": True, "state_ini": True, "git_jira": True,
                  "vendor_apps_started": False, "network_used": False, "catalog_hashes": {product: hashlib.sha256(json.dumps(Catalog.load(product), sort_keys=True).encode()).hexdigest() for product in ("inca", "silver")}}
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0

    @classmethod
    def portable_runtime_check(cls):
        import os
        import re
        import sys
        from .runtime import Runtime
        from ..silEinrichten import SilEinrichten,SilverInstallation
        packaged=getattr(sys,"frozen",False) or "__compiled__" in globals()
        result={"packaged":packaged,"self_contained_workers":False,"bundled_runtime":False}
        if not packaged:
            return result
        executable=Path(sys.executable).resolve()
        if executable.name.casefold() in ("python.exe","pythonw.exe","py.exe"):
            raise AssertionError("Packaged application uses external Python")
        command=SilEinrichten.launch_command()
        worker,args=SilverInstallation.worker_launch_command("start_worker.py","worker.json","setup.exe")
        if Path(command[0]).resolve()!=executable or Path(worker).resolve()!=executable or "start_worker.py" in args:
            raise AssertionError("Worker does not restart packaged executable")
        from ..silver.connection import SilverConnection
        api_command=SilverConnection.worker_launch_command("C:/Silver")
        if Path(api_command[0]).resolve()!=executable or api_command[1]!="--silver-api-worker":
            raise AssertionError("Silver API worker depends on external Python")
        import psutil
        dependencies={Path(entry.path).resolve() for entry in psutil.Process().memory_maps() if re.fullmatch(r"python[0-9_]*\.dll|qt6[^/\\]*\.dll",Path(entry.path).name,re.I)}
        root=executable.parent
        if not dependencies or any(not dependency.is_relative_to(root) for dependency in dependencies):
            raise AssertionError("Python/Qt runtime loaded outside distribution")
        result.update(self_contained_workers=True,bundled_runtime=True)
        return result

    @classmethod
    def api_worker_self_test(cls):
        import os,subprocess,sys,tempfile
        with tempfile.TemporaryDirectory() as folder:
            destination=Path(folder)/"worker.json"
            process=subprocess.run([sys.executable,"--silver-api-worker-test",str(destination)],input=json.dumps({"op":"self_test"})+"\n",capture_output=True,text=True,encoding="utf-8",timeout=25,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            if process.returncode or 'worker_ok' not in process.stdout:
                raise AssertionError("Packaged Silver API worker/pipe failed: "+process.stderr)
            result=json.loads(destination.read_text(encoding="utf-8"))
            if not result.get("external_process"):
                raise AssertionError("Packaged external process launcher failed")
            if result["pid"]==os.getpid() or Path(result["executable"]).resolve()!=Path(sys.executable).resolve():
                raise AssertionError("Silver API worker did not restart the packaged EXE")
            return True

    @classmethod
    def offline_driver_check(cls):
        import tempfile
        from unittest.mock import patch
        from .runtime import Runtime
        from .driver_archive import DriverArchive
        root=Runtime.project_root()/"drivers"
        manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
        if manifest.get("storage")!="zip":raise AssertionError("Offline driver archives missing")
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(Runtime,"data_root",return_value=Path(folder)):
                for version in manifest["versions"]:
                    if not DriverArchive.unpack(root/version/"edgedriver.zip").is_file():raise AssertionError("Offline driver unpack failed")
        return True
