import tempfile
import unittest
from pathlib import Path
from source.core.config import Config
from source.core.user_config import UserConfig

class UserConfigTests(unittest.TestCase):
    @classmethod
    def test_export_only_user_including_custom_values(cls):
        with tempfile.TemporaryDirectory() as folder:
            local=Path(folder)/"local.ini";target=Path(folder)/"USER.ini"
            Config.ensure_state(local)
            parser=Config.parser(local);parser.set("USER","CustomValue","some value 100%")
            parser.set("USER","GitUserState","True");Config.write(local,parser)
            UserConfig.export(target,local)
            exported=Config.parser(target)
            assert exported.sections()==["USER"]
            assert exported.get("USER","CustomValue")=="some value 100%"
            assert exported.get("USER","GitUserState")=="True"

    @classmethod
    def test_import_overwrites_user_preserves_machine_and_other_user_values(cls):
        with tempfile.TemporaryDirectory() as folder:
            local=Path(folder)/"local.ini";export=Path(folder)/"USER.ini"
            Config.ensure_state(local)
            before=Config.parser(local)
            export.write_text("[USER]\nGitUserState=True\nGitUserLicenceState=True\nCustom=extra\n",encoding="utf-8")
            UserConfig.import_file(export,local)
            after=Config.parser(local)
            assert dict(after["PATH"])==dict(before["PATH"])
            assert dict(after["STATE"])==dict(before["STATE"])
            assert after.get("USER","GitUserState")=="True"
            assert after.get("USER","JiraUserState")==before.get("USER","JiraUserState")
            assert after.get("USER","Custom")=="extra"

    @classmethod
    def test_invalid_import_never_changes_configuration(cls):
        for text in ("[USER]\nGitUserState=yes\n", "[PATH]\nsilverInstallerPath=bad\n", "[USER]\nGitUserState=True\n[STATE]\nGitInstallationState=True\n"):
            with tempfile.TemporaryDirectory() as folder:
                local=Path(folder)/"local.ini";export=Path(folder)/"bad.ini"
                Config.ensure_state(local);before=local.read_bytes()
                export.write_text(text,encoding="utf-8")
                with unittest.TestCase().assertRaises(ValueError):UserConfig.import_file(export,local)
                assert local.read_bytes()==before

    @classmethod
    def test_export_cannot_replace_local_ini(cls):
        with tempfile.TemporaryDirectory() as folder:
            local=Path(folder)/"local.ini";Config.ensure_state(local)
            before=local.read_bytes()
            with unittest.TestCase().assertRaises(ValueError):UserConfig.export(local,local)
            assert local.read_bytes()==before
