from pathlib import Path
from xml.etree import ElementTree as ET
from unittest.mock import patch
import pytest
from source.silver.xml_flash import SilverXmlFlash as Xml
from source.silver.parameter_files import SilverParameterFiles as Files
from source.silver.methods import Silver

@pytest.fixture(autouse=True)
def explicit_xml_trial():
    with patch.object(Files,"XML_FLASH_TRIAL",True):
        yield


@pytest.fixture
def project(tmp_path):
    slave,master=Files.TARGETS
    nodes=[]
    for name,role in ((slave,"Slave"),(master,"Master")):
        folder=tmp_path/role;folder.mkdir()
        (folder/name).write_text('<workspace><modules><module><sil-line>'+role+'/vECU.dll -d "${variant_code_string_file}" -Pkeep.dcm</sil-line></module></modules><parameters><param><name>variant_code_string_file</name><value>default.aed</value></param></parameters></workspace>',encoding="utf-8")
        nodes.append('<sfu><uuid>'+role+'</uuid><path>'+role+'/'+name+'</path><enabled>true</enabled><parameters><param><name>Parameter_files</name><value>-Pold.dcm</value></param><param><name>variant_code_string_file</name><value>old.aed</value></param><param><name>Keep</name><value>unchanged</value></param></parameters></sfu>')
    setup=tmp_path/"Setup.sil"
    setup.write_bytes(('<?xml version="1.0" encoding="utf-8"?>\r\n<workspace>\r\n<modules>'+''.join(nodes)+'</modules>\r\n<parameters><param><name>KeepGlobal</name><value>yes</value></param></parameters><!-- keep comment -->\r\n</workspace>').encode("utf-8"))
    return setup,slave,master


def test_only_selected_main_sfu_parameters_change_and_bound_sources_stay_untouched(project):
    setup,slave,master=project
    original=setup.read_bytes();source=(setup.parent/"Slave"/slave).read_bytes()
    master_before=ET.tostring(ET.fromstring(original).findall("./modules/sfu")[1])
    changes={slave:{"files":["first.dcm","extra & file.DCM"],"variant":"new & file.aed"}}
    plan=Xml.prepare(changes,setup)
    assert [item[0] for item in plan]==[setup]
    assert setup.read_bytes()==original
    Xml.commit(plan)
    root=ET.parse(setup).getroot()
    assert ET.tostring(root.findall("./modules/sfu")[1])==master_before
    values={node.findtext("name"):node.findtext("value") for node in root.findall("./modules/sfu")[0].findall("./parameters/param")}
    assert values=={"Parameter_files":'-Pfirst.dcm -P"extra & file.DCM"',"variant_code_string_file":"new & file.aed","Keep":"unchanged"}
    assert (setup.parent/"Slave"/slave).read_bytes()==source
    assert b"<!-- keep comment -->\r\n" in setup.read_bytes()
    assert setup.with_suffix(".sil.siLAssistent_xml_flash.bak").read_bytes()==original
    assert Xml.prepare(changes,setup)==[]
    Xml.restore(plan);assert setup.read_bytes()==original


def test_literal_aed_argument_only_changes_affected_sfu(project):
    setup,slave,master=project
    path=setup.parent/"Slave"/slave
    path.write_text(path.read_text(encoding="utf-8").replace('"${variant_code_string_file}"','old.aed'),encoding="utf-8")
    master_before=(setup.parent/"Master"/master).read_bytes()
    plan=Xml.prepare({slave:{"files":["new.dcm"],"variant":"new.aed"}},setup)
    assert {item[0] for item in plan}=={setup,path}
    Xml.commit(plan)
    assert '-d "${variant_code_string_file}"' in ET.parse(path).findtext("./modules/module/sil-line")
    assert ET.parse(path).findtext("./parameters/param/value")=="default.aed"
    assert (setup.parent/"Master"/master).read_bytes()==master_before


def test_grouped_payload_updates_both_without_other_xml_edits(project):
    setup,slave,master=project
    changes={name:{"files":[name+".dcm"],"variant":"both.aed"} for name in (slave,master)}
    plan=Xml.prepare(changes,setup);Xml.commit(plan)
    assert len(plan)==1
    for node in ET.parse(setup).findall("./modules/sfu"):
        values={p.findtext("name"):p.findtext("value") for p in node.findall("./parameters/param")}
        assert values["variant_code_string_file"]=="both.aed"
        assert values["Keep"]=="unchanged"


def test_concurrent_change_prevents_any_write(project):
    setup,slave,master=project
    plan=Xml.prepare({slave:["new.dcm"]},setup)
    setup.write_bytes(setup.read_bytes()+b" ")
    newer=setup.read_bytes()
    with pytest.raises(RuntimeError,match="zwischenzeitlich"):Xml.commit(plan)
    assert setup.read_bytes()==newer


def test_xml_apply_uses_disk_and_open_not_sfu_api_writes(project):
    setup,slave,master=project;events=[]
    with patch.object(Silver,"stop",side_effect=lambda **kw:events.append("stop")),patch.object(Silver,"save",side_effect=lambda *a,**kw:events.append("save")),patch.object(Silver,"open",side_effect=lambda *a,**kw:events.append("open")),patch.object(Files,"verify_flash",return_value=True),patch.object(Silver,"set_sfu_property") as write,patch.object(Silver,"reload") as reload:
        Files.apply_and_reload({slave:{"files":["new.dcm"],"variant":"new.aed"}},str(setup))
    assert events==["stop","save","open"]
    write.assert_not_called();reload.assert_not_called()
    assert "new.aed" in setup.read_text(encoding="utf-8")


def test_failed_load_restores_exact_saved_xml(project):
    setup,slave,master=project;original=setup.read_bytes()
    with patch.object(Silver,"stop"),patch.object(Silver,"save",return_value=True),patch.object(Silver,"open",side_effect=RuntimeError("load failed")):
        with pytest.raises(RuntimeError,match="zurückgesetzt"):
            Files.apply_and_reload({slave:{"files":["new.dcm"],"variant":"new.aed"}},str(setup))
    assert setup.read_bytes()==original


def test_failed_readback_also_restores_xml(project):
    setup,slave,master=project;original=setup.read_bytes()
    with patch.object(Silver,"stop"),patch.object(Silver,"save",return_value=True),patch.object(Silver,"open"),patch.object(Files,"verify_flash",return_value=False):
        with pytest.raises(RuntimeError,match="andere DCM"):
            Files.apply_and_reload({slave:["new.dcm"]},str(setup))
    assert setup.read_bytes()==original


def test_partial_commit_failure_restores_files_already_written(project):
    setup,slave,master=project
    path=setup.parent/"Slave"/slave
    path.write_text(path.read_text(encoding="utf-8").replace('"${variant_code_string_file}"','old.aed'),encoding="utf-8")
    plan=Xml.prepare({slave:{"files":["new.dcm"],"variant":"new.aed"}},setup)
    original={p:data for p,data,_ in plan};actual_write=Xml.write_atomic;calls=[]
    def fail_second(path,data):
        calls.append(path)
        if len(calls)==2:raise OSError("write failed")
        actual_write(path,data)
    with patch.object(Xml,"write_atomic",side_effect=fail_second):
        with pytest.raises(OSError,match="write failed"):Xml.commit(plan)
    assert all(path.read_bytes()==data for path,data in original.items())


def test_legacy_api_can_be_selected_without_xml_writes():
    with patch.object(Files,"XML_FLASH_TRIAL",False),patch.object(Files,"apply_via_api",return_value="legacy") as legacy,patch.object(Xml,"prepare") as prepare:
        assert Files.apply_and_reload({},"setup.sil")=="legacy"
        legacy.assert_called_once_with({},"setup.sil",None)
        prepare.assert_not_called()
