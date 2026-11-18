import tempfile
import unittest
import runpy
from pathlib import Path
from unittest.mock import patch
from source.core.config import Config
from source.core import build_settings
from source.core.release_paths import ReleasePaths
from tools.embed_build_settings import EmbedBuildSettings

class ReleasePathTests(unittest.TestCase):
    @classmethod
    def values(cls):
        return {"silverInstallerPath":r"\\server\software\SilverSetup_Y-2026.09.exe","silSetupPath":r"\\server\setups\SimFiles","GitInstallationPath":r"\\server\software\git.exe","GitSetupRepo":"https://mercedes-benz.ghe.com/other/SimFiles.git"}

    @classmethod
    def test_build_embeds_four_paths_and_installer_ini_uses_same_values(cls):
        with tempfile.TemporaryDirectory() as folder:
            ini=Path(folder)/"update.ini";output=Path(folder)/"build_settings.py"
            parser=Config.parser(ini)
            parser["UPDATE"]={"supportMail":"support@example.invalid","silverLicences":"27031@host.example"}
            parser["PATH"]=cls.values();Config.write(ini,parser)
            EmbedBuildSettings.write(output,ini)
            embedded=runpy.run_path(str(output))["RELEASE_PATHS"]
            assert embedded==cls.values()
            target=Path(folder)/"installer.ini"
            Config.export_installation_config(target,paths=embedded)
            assert all(Config.parser(target).get("PATH",key)==value for key,value in embedded.items())

    @classmethod
    def test_new_build_preserves_all_existing_local_paths(cls):
        with tempfile.TemporaryDirectory() as folder:
            ini=Path(folder)/"local.ini";Config.ensure_state(ini)
            before=Config.state(ini)
            with patch.object(build_settings,"RELEASE_PATHS",cls.values()):
                Config.ensure_state(ini)
                assert Config.state(ini)==before
            changed={**cls.values(),"GitInstallationPath":r"\\server\new\git.exe"}
            with patch.object(build_settings,"RELEASE_PATHS",changed):
                assert Config.state(ini)==before

    @classmethod
    def test_missing_path_fails_build(cls):
        with tempfile.TemporaryDirectory() as folder:
            ini=Path(folder)/"invalid.ini";ini.write_text("[PATH]\nsilverInstallerPath=wrong.exe\n",encoding="utf-8")
            with unittest.TestCase().assertRaises(ValueError):ReleasePaths.read(ini)

    @classmethod
    def test_json_style_doubled_unc_paths_are_normalized(cls):
        value=r"\\server\software\git.exe"
        assert ReleasePaths.normalize_path(value.replace("\\","\\\\"))==value
