from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from source.core.config import Config

class InstallationStateTests(unittest.TestCase):
    @classmethod
    def test_first_creation_has_exact_keys_and_values(cls):
        expected = {"GitUserState": "False", "JiraUserState": "False", "GitInstallationState": "False",
                    "InstalledSilverVersion": "",
                    "GitSetupRepo": "https://mercedes-benz.ghe.com/devM286/SimFiles.git",
                    "silverInstallerPath": r"\\smtcft0028prj.rd.corpintra.net\me7work$\Projekte\M286\04_Software_EDL\30_SiL\Silver_Software\SilverSetup_Y-2026.03-1.exe"}
        expected["silSetupVersionCounter"] = "0"
        expected["DriveSetupLocalPath"] = ""
        expected["silSetupPath"] = Config.STATE_DEFAULTS["silSetupPath"]
        expected["GitUserLicenceState"] = "False"
        expected["GitInstallationPath"] = Config.STATE_DEFAULTS["GitInstallationPath"]
        expected["GitLocalRepoPath"] = ""
        expected.update(DcmEditorPath="",SetupAutoConnect="False",FlashFilesGrouped="False",SetupHeadless="False",SetupExitNow="False")
        assert Config.STATE_DEFAULTS == expected
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "siLAssistent.ini"
            Config.ensure_state(path)
            assert (dict(Config.parser(path)["STATE"]) | dict(Config.parser(path)["USER"]) | dict(Config.parser(path)["PATH"])) == expected
            assert Config.state(path)["GitUserState"] is False
            assert Config.state(path)["InstalledSilverVersion"] is None

    @classmethod
    def test_existing_values_and_application_settings_survive(cls):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "siLAssistent.ini"
            path.write_text("[APPLICATION]\nupdate_ini_path=custom.ini\n[STATE]\nGitUserState=True\nInstalledSilverVersion=W-2024.09\nCustomValue=keep\n", encoding="utf-8")
            Config.ensure_state(path)
            Config.ensure_state(path)
            state = Config.state(path)
            assert state["GitUserState"] is True and state["InstalledSilverVersion"] == "W-2024.09"
            parser = Config.parser(path)
            assert parser["APPLICATION"]["update_ini_path"] == "custom.ini"
            assert parser["STATE"]["CustomValue"] == "keep"
            Config.set_state("JiraUserState", True, path)
            assert Config.state(path)["GitUserState"] is True and Config.state(path)["JiraUserState"] is True

    @classmethod
    def test_parallel_state_writes_preserve_both_values(cls):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "siLAssistent.ini"
            Config.ensure_state(path)
            with ThreadPoolExecutor(max_workers=2) as pool:
                tasks = [pool.submit(Config.set_state, key, True, path) for key in ("GitUserState", "JiraUserState")]
                for task in tasks:
                    task.result(timeout=15)
            state = Config.state(path)
            assert state["GitUserState"] is True and state["JiraUserState"] is True

    @classmethod
    def test_build_never_ships_developer_state(cls):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "dev.ini"
            Config.ensure_state(source)
            Config.set_state("GitUserState", True, source)
            Config.set_state("InstalledSilverVersion", "dev-only", source)
            target = Path(temp) / "stage" / "siLAssistent.ini"
            with patch.object(Config, "path", return_value=source):
                Config.export_installation_config(target)
            assert (dict(Config.parser(target)["STATE"]) | dict(Config.parser(target)["USER"]) | dict(Config.parser(target)["PATH"])) == Config.STATE_DEFAULTS
            assert Config.state(source)["InstalledSilverVersion"] == "dev-only"

    @classmethod
    def test_inno_state_defaults_never_overwrite_existing_keys(cls):
        template = (Path(__file__).resolve().parents[1] / "_iss/siLAssistent.iss").read_text(encoding="utf-8")
        assert 'Flags: onlyifdoesntexist uninsneveruninstall' in template
        for key in Config.STATE_DEFAULTS:
            assert f'Key: "{key}"' not in template
        assert 'Excludes: "siLAssistent.ini"' in template

    @classmethod
    def test_invalid_boolean_state_is_not_silently_accepted(cls):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "siLAssistent.ini"
            with unittest.TestCase().assertRaises(TypeError):
                Config.set_state("GitUserState", "yes", path)

    @classmethod
    def test_existing_installation_migrates_default_share_to_ini_folder(cls):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "siLAssistent.ini"
            path.write_text("[APPLICATION]\nupdate_ini_path=" + Config.LEGACY_UPDATE_INI + "\n[STATE]\naktuellSilverVersion=custom-SilverSetup_Y-2026.09.exe\n", encoding="utf-8")
            Config.ensure_state(path)
            parser = Config.parser(path)
            assert parser["APPLICATION"]["update_ini_path"] == Config.UPDATE_INI
            assert parser["PATH"]["silverInstallerPath"] == "custom-SilverSetup_Y-2026.09.exe"
            assert all(not parser.has_option(section,"aktuellSilverVersion") for section in parser.sections())

    @classmethod
    def test_user_section_wins_and_legacy_license_migrates(cls):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"state.ini"
            path.write_text("[STATE]\nGitUserState=False\nGitLicenceState=True\n[USER]\nGitUserState=True\nJiraUserState=True\n",encoding="utf-8")
            state=Config.state(path)
            assert state["GitUserState"] is True
            assert state["GitUserLicenceState"] is True
            parser=Config.parser(path)
            assert parser["USER"]["GitUserLicenceState"]=="True"
            assert "GitUserState" not in parser["STATE"]
            assert "GitLicenceState" not in parser["STATE"]

    @classmethod
    def test_paths_move_without_losing_values(cls):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"state.ini"
            path.write_text("[STATE]\nGitLocalRepoPath=D:/old\nInstalledSilverVersion=Y-2026.03-1\n[PATH]\nGitLocalRepoPath=D:/chosen\n",encoding="utf-8")
            state=Config.state(path)
            parser=Config.parser(path)
            assert state["GitLocalRepoPath"]=="D:/chosen"
            assert parser["PATH"]["InstalledSilverVersion"]=="Y-2026.03-1"
            assert "GitLocalRepoPath" not in parser["STATE"]
            Config.set_state("GitInstallationPath","custom.exe",path)
            assert Config.parser(path)["PATH"]["GitInstallationPath"]=="custom.exe"

    @classmethod
    def test_setup_source_sync_preserves_existing_path_target_and_counter(cls):
        import configparser
        with tempfile.TemporaryDirectory() as folder:
            ini=Path(folder)/"local.ini"
            Config.set_state("silSetupPath",r"\\server\old\SimFiles",ini)
            Config.set_state("DriveSetupLocalPath",r"C:\Work\SimFiles",ini)
            Config.set_state("silSetupVersionCounter","12",ini)
            parser=configparser.ConfigParser(interpolation=None)
            parser.read_dict({"UPDATE":{"silSetupPath":r"\\server\new\SimFiles"}})
            Config.sync_update_paths(parser,ini)
            state=Config.state(ini)
            assert state["silSetupPath"]==r"\\server\old\SimFiles"
            assert state["DriveSetupLocalPath"]==r"C:\Work\SimFiles"
            assert state["silSetupVersionCounter"]=="12"
            parser.remove_option("UPDATE","silSetupPath")
            Config.sync_update_paths(parser,ini)
            assert Config.state(ini)["silSetupPath"]==r"\\server\old\SimFiles"

    @classmethod
    def test_obsolete_update_state_removed_from_existing_ini(cls):
        with tempfile.TemporaryDirectory() as folder:
            ini=Path(folder)/"existing.ini"
            ini.write_text("[STATE]\nUpdateState = True\n[USER]\nGitUserState = True\n",encoding="utf-8")
            Config.ensure_state(ini)
            assert not Config.parser(ini).has_option("STATE","UpdateState")
            assert "UpdateState" not in Config.state(ini)
            assert Config.state(ini)["GitUserState"] is True

    @classmethod
    def test_new_silver_path_wins_and_old_alias_is_removed(cls):
        with tempfile.TemporaryDirectory() as folder:
            ini=Path(folder)/"state.ini"
            ini.write_text("[PATH]\nsilverInstallerPath=new.exe\naktuellSilverVersion=old.exe\n[STATE]\naktuellSilverVersion=older.exe\n",encoding="utf-8")
            Config.ensure_state(ini)
            parser=Config.parser(ini)
            assert parser.get("PATH","silverInstallerPath")=="new.exe"
            assert all(not parser.has_option(section,"aktuellSilverVersion") for section in parser.sections())

    @classmethod
    def test_empty_and_legacy_silver_version_are_detected_as_unknown(cls):
        with tempfile.TemporaryDirectory() as folder:
            ini=Path(folder)/"local.ini"
            Config.ensure_state(ini)
            assert Config.parser(ini).get("PATH","InstalledSilverVersion")==""
            for value in ("", "None", " none "):
                Config.set_state("InstalledSilverVersion",value,ini)
                assert Config.state(ini)["InstalledSilverVersion"] is None
            Config.set_state("InstalledSilverVersion",None,ini)
            assert Config.parser(ini).get("PATH","InstalledSilverVersion")==""

    @classmethod
    def test_export_does_not_leak_developer_application_settings(cls):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/"dev.ini";target=Path(folder)/"installer.ini"
            source.write_text("[APPLICATION]\nsilver_home=C:/Developer/Silver\nrelease_paths_revision=old-machine\n",encoding="utf-8")
            with patch.object(Config,"path",return_value=source):Config.export_installation_config(target)
            assert not Config.parser(target).has_option("APPLICATION","silver_home")
            assert not Config.parser(target).has_option("APPLICATION","release_paths_revision")
