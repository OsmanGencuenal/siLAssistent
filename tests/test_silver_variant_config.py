import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
import pytest
from source.silver.variant_config import SilverVariantConfig as Config

SOURCE='<workspace>\n<modules><module><sil-line>ECM/Slave/vECU.dll -d ECM/old.aed -Pdata.dcm -Z 5562</sil-line></module><module><sil-line>python.dll other.py</sil-line></module></modules>\n<parameters><param><name>variant_code_string_file</name><value>ECM/old.aed</value></param><param><name>Other</name><value>keep</value></param></parameters>\n</workspace>'

def test_variant_binds_actual_vecu_argument_and_preserves_other_settings():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);sfu=root/"Slave.sil";sfu.write_text(SOURCE,encoding="utf-8")
        original=sfu.read_bytes()
        changes={"Slave.sil":{"variant":"ECM/new & selected.aed","files":["data.dcm"]}}
        plan=Config.prepare(changes,str(root/"Setup.sil"),{"Slave.sil":{"path":"Slave.sil"}})
        assert sfu.read_bytes()==original
        Config.apply(plan)
        xml=ET.fromstring(sfu.read_bytes())
        line=xml.find("./modules/module/sil-line").text
        assert '-d "${variant_code_string_file}"' in line
        assert "-Pdata.dcm -Z 5562" in line
        assert xml.find("./parameters/param/value").text=="ECM/new & selected.aed"
        assert sfu.with_suffix(".sil.siLAssistent.bak").read_bytes()==original
        assert Config.prepare(changes,str(root/"Setup.sil"),{"Slave.sil":{"path":"Slave.sil"}})==[]


def test_concurrent_sfu_edit_is_not_overwritten():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);sfu=root/"Slave.sil";sfu.write_text(SOURCE,encoding="utf-8")
        plan=Config.prepare({"Slave.sil":{"variant":"new.aed"}},str(root/"Setup.sil"),{"Slave.sil":{"path":"Slave.sil"}})
        sfu.write_text(SOURCE+" ",encoding="utf-8")
        with pytest.raises(RuntimeError,match="zwischenzeitlich"):
            Config.apply(plan)
        assert sfu.read_text(encoding="utf-8")==SOURCE+" "


def test_verification_checks_expanded_vecu_argument_not_just_parameter():
    from unittest.mock import patch
    from source.silver.parameter_files import SilverParameterFiles as Files
    from source.silver.methods import Silver
    changes={"Slave.sil":{"variant":"new.aed"}}
    entries={"Slave.sil":{"uuid":"slave","variant":"new.aed"}}
    with patch.object(Files,"entries",return_value=entries),patch.object(Silver,"get_module_uuids",return_value=["slave::vecu"]),patch.object(Silver,"get_module_properties",return_value={"preview_sil_line":"vECU.dll -d old.aed"}):
        assert not Files.verify_variants(changes)
    with patch.object(Files,"entries",return_value=entries),patch.object(Silver,"get_module_uuids",return_value=["slave::vecu"]),patch.object(Silver,"get_module_properties",return_value={"preview_sil_line":'vECU.dll -d "new.aed"'}):
        assert Files.verify_variants(changes)


def test_stale_editor_reopens_only_after_verified_mismatch():
    from unittest.mock import patch,Mock
    from source.silver.parameter_files import SilverParameterFiles as Files
    from source.silver.methods import Silver
    events=[]
    with patch.object(Config,"prepare",return_value=[]),patch.object(Config,"apply"),patch.object(Files,"entries",return_value={}),patch.object(Files,"update_many",side_effect=lambda changes:events.append("update")),patch.object(Files,"verify_variants",side_effect=[False,True]),patch.object(Silver,"stop"),patch.object(Silver,"save",return_value=True),patch.object(Silver,"reload",side_effect=lambda **kw:events.append("reload")),patch.object(Silver,"open",side_effect=lambda *a,**kw:events.append("open")):
        Files.apply_via_api({"Slave.sil":{"variant":"new.aed","files":["one.dcm"]}},"setup.sil")
    assert events==["update","reload","open","update","reload"]


def test_persisting_variant_mismatch_is_reported_as_failure():
    from unittest.mock import patch
    from source.silver.parameter_files import SilverParameterFiles as Files
    from source.silver.methods import Silver
    with patch.object(Config,"prepare",return_value=[]),patch.object(Config,"apply"),patch.object(Files,"entries",return_value={}),patch.object(Files,"update_many"),patch.object(Files,"verify_variants",return_value=False),patch.object(Silver,"stop"),patch.object(Silver,"save",return_value=True),patch.object(Silver,"reload"),patch.object(Silver,"open"):
        with pytest.raises(RuntimeError,match="nicht übernommen"):
            Files.apply_via_api({"Slave.sil":{"variant":"new.aed","files":["one.dcm"]}},"setup.sil")
