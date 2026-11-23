from pathlib import Path
import ast
import json
import unittest

class BuildContractTests(unittest.TestCase):
    @classmethod
    def test_no_reference_material_shipped(cls):
        root = Path(__file__).resolve().parents[1]
        build = (root / "tools/build_siLAssistent.ps1").read_text(encoding="utf-8")
        assert "Silver_UserGuide.pdf" not in build and "docs/reference" not in build
        for product in ("inca", "silver"):
            assert f"source/{product}/catalog.json" in build
        assert "--include-module=pythoncom" in build
        assert "--include-module=pywintypes" in build
        assert "--include-module=win32timezone" in build

    @classmethod
    def test_title_only_methods_are_marked(cls):
        root = Path(__file__).resolve().parents[1]
        catalog = json.loads((root / "source/inca/catalog.json").read_text(encoding="utf-8"))
        assert any(row["title_only"] for row in catalog["methods"])
        assert all(not row["signature_documented"] for row in catalog["methods"] if row["title_only"])

    @classmethod
    def test_silver_reference_versions_are_explicit(cls):
        root = Path(__file__).resolve().parents[1]
        catalog = json.loads((root / "source/silver/catalog.json").read_text(encoding="utf-8"))
        assert catalog["manual_version"] == "Y-2026.03"
        assert catalog["supplement_version"] == "W-2024.09"
        assert len(catalog["methods"]) == 74

    @classmethod
    def test_release_uses_complete_suite_and_only_runtime_icons(cls):
        root=Path(__file__).resolve().parents[1]
        build=(root/"tools/build_siLAssistent.ps1").read_text(encoding="utf-8")
        assert 'tools\\run_tests.py' in build
        runner=(root/"tools/run_tests.py").read_text(encoding="utf-8")
        assert '"-vv"' in runner and "idle_timeout=180" in runner
        assert "--nofollow-import-to=pytest" in build
        assert "--include-data-dir=$Root\\icons=icons" not in build
        assert "check_distribution.py" in build
        assert (root/"build_siLAssistent.bat").is_file()
        assert not (root/"build.bat").exists()

    @classmethod
    def test_selenium_manager_is_not_added_twice(cls):
        build=(Path(__file__).resolve().parents[1]/"tools/build_siLAssistent.ps1").read_text(encoding="utf-8")
        assert "--include-package=selenium" in build
        assert "--include-data-files=$SeleniumManager=" not in build
        assert "--include-package-data=selenium" not in build
        assert "--nofollow-import-to=comtypes.test" in build

    @classmethod
    def test_offline_driver_archives_are_packaged_after_compilation(cls):
        build=(Path(__file__).resolve().parents[1]/"tools/build_siLAssistent.ps1").read_text(encoding="utf-8")
        assert 'tools\\package_runtime.py' in build
        assert '--noinclude-data-files=selenium/webdriver/common/macos/*' in build
        assert "--include-data-dir=$Root\\drivers=drivers" not in build

    @classmethod
    def test_default_build_copies_installer_to_requested_share(cls):
        root=Path(__file__).resolve().parents[1]
        build=(root/"tools/build_siLAssistent.ps1").read_text(encoding="utf-8")
        batch=(root/"build_siLAssistent.bat").read_text(encoding="utf-8")
        assert "-LocalOnly -CreateInstaller" not in batch
        assert "$InstallerCopyDirectory -and -not $LocalOnly" in build
        assert "Move-Item -LiteralPath $TemporaryInstaller -Destination $CopiedInstaller -Force" in build
        assert "Get-FileHash -LiteralPath $TemporaryInstaller -Algorithm SHA256" in build

    @classmethod
    def test_installer_offers_checked_optional_start_on_finish(cls):
        installer=(Path(__file__).resolve().parents[1]/"_iss/siLAssistent.iss").read_text(encoding="utf-8")
        run=installer.split("[Run]",1)[1]
        assert 'Description: "siLAssistent starten"' in run
        assert 'WorkingDir: "{app}"' in run
        assert "nowait postinstall skipifsilent" in run
        assert "unchecked" not in run

    @classmethod
    def test_installer_always_shows_directory_and_build_waits_at_finish(cls):
        root=Path(__file__).resolve().parents[1]
        installer=(root/"_iss/siLAssistent.iss").read_text(encoding="utf-8")
        batch=(root/"build_siLAssistent.bat").read_text(encoding="utf-8")
        assert "DisableDirPage=no" in installer
        assert "### BUILD ERFOLGREICH ABGESCHLOSSEN ###" in batch and "### BUILD FEHLGESCHLAGEN ###" in batch
        assert "pause" in batch and "exit /b %BuildResult%" in batch

    @classmethod
    def test_uninstall_exports_before_removal_and_has_direct_shortcut(cls):
        installer=(Path(__file__).resolve().parents[1]/"_iss/siLAssistent.iss").read_text(encoding="utf-8")
        assert "function InitializeUninstall(): Boolean;" in installer
        assert "MB_YESNOCANCEL" in installer and "GetSaveFileName" in installer
        assert "--export-user-config" in installer and "ExitCode <> 0" in installer
        assert 'siLAssistent entfernen' in installer and '--uninstall ""{uninstallexe}""' in installer

    @classmethod
    def test_version_prompt_and_desktop_choice_are_connected(cls):
        root=Path(__file__).resolve().parents[1]
        installer=(root/"_iss/siLAssistent.iss").read_text(encoding="utf-8")
        batch=(root/"build_siLAssistent.bat").read_text(encoding="utf-8")
        assert "select_build_version.py" in batch
        assert batch.index("select_build_version.py")<batch.index("build_siLAssistent.ps1")
        assert '[Tasks]' in installer and 'Tasks: desktopicon' in installer
        assert 'WizardImageStretch=no' in installer and 'DisableWelcomePage=no' in installer

    @classmethod
    def test_uninstall_deletes_only_local_configuration_and_lock(cls):
        installer=(Path(__file__).resolve().parents[1]/"_iss/siLAssistent.iss").read_text(encoding="utf-8")
        cleanup=installer.split("[UninstallDelete]",1)[1].split("[Code]",1)[0]
        assert 'Name: "{app}\\siLAssistent.ini"' in cleanup
        assert 'Name: "{app}\\siLAssistent.ini.lock"' in cleanup
        assert 'Type: dirifempty; Name: "{app}"' in cleanup
        assert "filesandordirs" not in cleanup

    @classmethod
    def test_standalone_gate_requires_isolated_uia_worker(cls):
        root=Path(__file__).resolve().parents[1]
        gate=(root/"tools/test_standalone.ps1").read_text(encoding="utf-8")
        smoke=(root/"source/core/smoke.py").read_text(encoding="utf-8")
        assert '"silver_ui_worker"' in gate
        assert 'cls.ui_worker_self_test()' in smoke
        assert 'SilverUiClient.command' in smoke


    @classmethod
    def test_default_installer_copy_publishes_complete_update_manifest(cls):
        build=(Path(__file__).resolve().parents[1]/'tools/build_siLAssistent.ps1').read_text(encoding='utf-8')
        default=build[build.index('if ($InstallerCopyDirectory -and -not $LocalOnly)'):build.index('    if ($PublishDirectory) {')]
        assert default.index('Move-Item -LiteralPath $TemporaryInstaller')<default.index('tools\\write_release_manifest.py')
        assert 'ini\\siLAssistent_Update.ini' in default
        assert '(Join-Path $Root "siLAssistent_Update.ini")' in default
        assert '--installer $CopiedInstaller --sha256 $LocalHash' in default
