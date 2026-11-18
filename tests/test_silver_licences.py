import tempfile
import unittest
import runpy
from pathlib import Path
from unittest.mock import Mock,patch
from source.silver.licences import SilverLicences
from source.core import build_settings
from source.core.config import Config
from source.core.release_paths import ReleasePaths
from source.silEinrichten import SilverInstallation
from tools.embed_build_settings import EmbedBuildSettings

class SilverLicenceTests(unittest.TestCase):
    @classmethod
    def test_build_embeds_current_ini_servers(cls):
        with tempfile.TemporaryDirectory() as folder:
            ini=Path(folder)/"update.ini"
            output=Path(folder)/"build_settings.py"
            ini.write_text("[UPDATE]\nsupportMail=support@example.invalid\nsilverLicences=27031@first.example,27031@second.example\n",encoding="utf-8")
            with ini.open("a",encoding="utf-8") as stream:
                stream.write("\n[PATH]\n"+"\n".join(key+"="+Config.STATE_DEFAULTS[key] for key in ReleasePaths.KEYS)+"\n")
            EmbedBuildSettings.write(output,ini)
            assert runpy.run_path(str(output))["SILVER_LICENCE_SERVERS"]==("27031@first.example","27031@second.example")
            ini.write_text("[UPDATE]\nsupportMail=support@example.invalid\nsilverLicences=27032@changed.example\n",encoding="utf-8")
            with ini.open("a",encoding="utf-8") as stream:
                stream.write("\n[PATH]\n"+"\n".join(key+"="+Config.STATE_DEFAULTS[key] for key in ReleasePaths.KEYS)+"\n")
            EmbedBuildSettings.write(output,ini)
            assert runpy.run_path(str(output))["SILVER_LICENCE_SERVERS"]==("27032@changed.example",)

    @classmethod
    def test_embedded_values_do_not_read_previous_configuration(cls):
        with patch.object(build_settings,"SILVER_LICENCE_SERVERS",("27031@first.example",)),patch.object(SilverLicences,"read",side_effect=AssertionError("No profile or network read allowed")):
            assert SilverLicences.wizard_value()=="27031@first.example"
            assert SilverLicences.environment_value()=="27031@first.example"

    @classmethod
    def test_missing_or_invalid_servers_fail_before_build(cls):
        for value in ("", "0@host", "65536@host", "server.example", "27031@host /VERYSILENT"):
            with unittest.TestCase().assertRaises(ValueError):
                SilverLicences.normalize(value)

    @classmethod
    def test_windows_environment_uses_semicolon(cls):
        with patch.object(build_settings,"SILVER_LICENCE_SERVERS",("27031@one.example","27031@two.example")):
            assert SilverLicences.environment_value()=="27031@one.example;27031@two.example"
            assert SilverLicences.wizard_value()=="27031@one.example,27031@two.example"

    @classmethod
    def test_wizard_sets_servers_and_options_without_prior_installation(cls):
        window=Mock()
        edit=Mock()
        edit.is_visible.return_value=True
        edit.is_enabled.return_value=True
        current={"value":"27031@old.example,27031@old.example"}
        edit.get_value.side_effect=lambda: current["value"]
        edit.set_edit_text.side_effect=lambda value: current.update(value=value)
        edit.iface_value.SetValue.side_effect=lambda value: current.update(value=value)
        window.descendants.return_value=[edit]
        with patch.object(build_settings,"SILVER_LICENCE_SERVERS",("27031@new.example",)),patch.object(SilverInstallation,"set_option") as option:
            SilverInstallation.configure_license(window)
            edit.set_edit_text.assert_any_call("")
            edit.iface_value.SetValue.assert_called_once_with("27031@new.example")
            assert current["value"]=="27031@new.example"
            assert option.call_args_list[0].args[2] is True
            assert option.call_args_list[1].args[2] is False

    @classmethod
    def test_existing_servers_are_cleared_before_any_new_value(cls):
        edit=Mock()
        state={"value":"27031@new.example,27031@new.example"}
        events=[]
        edit.get_value.side_effect=lambda: state["value"]
        edit.set_edit_text.side_effect=lambda value: (events.append(("clear",value)),state.update(value=value))
        edit.iface_value.SetValue.side_effect=lambda value: (events.append(("set",value)),state.update(value=value))
        SilverInstallation.replace_license_servers(edit,"27031@new.example")
        assert events==[("clear",""),("set","27031@new.example")]
        assert state["value"]=="27031@new.example"

    @classmethod
    def test_nonclearable_field_never_gets_new_servers_appended(cls):
        edit=Mock()
        edit.get_value.return_value="27031@old.example"
        with unittest.TestCase().assertRaisesRegex(RuntimeError,"gelöscht"):
            SilverInstallation.replace_license_servers(edit,"27031@new.example")
        assert all(call.args[0]=="" for call in edit.iface_value.SetValue.call_args_list)
        assert all(call.args[0]=="" for call in edit.set_edit_text.call_args_list)

    @classmethod
    def test_duplicate_result_is_not_accepted(cls):
        edit=Mock()
        edit.get_value.side_effect=["","","","27031@new.example,27031@new.example"]
        with unittest.TestCase().assertRaisesRegex(RuntimeError,"exakt"):
            SilverInstallation.replace_license_servers(edit,"27031@new.example")
