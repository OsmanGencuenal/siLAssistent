import unittest
from unittest.mock import patch
from source.silver.parameter_files import SilverParameterFiles as Files
from source.silver.methods import Silver

class ParameterFileTests(unittest.TestCase):
    @classmethod
    def test_path_roundtrip_preserves_spaces_and_windows_separators(cls):
        values=[r"ECM\Slave\first.dcm",r"C:\My Data\second.DCM"]
        assert Files.parse(Files.serialize(values))==values

    @classmethod
    def test_updates_only_parameter_files_in_named_sfu(cls):
        props={"slave":{"path":"ECM/ECM_MRG12_Slave.sil","parameters":{"Parameter_files":"-Pa.dcm","Other":"keep"}},"other":{"path":"Other.sil","parameters":{}}}
        with patch.object(Silver,"get_top_level_sfu_uuids",return_value=list(props)),patch.object(Silver,"get_sfu_properties",side_effect=lambda uuid,**kw:props[uuid]),patch.object(Silver,"set_sfu_property",return_value=True) as write:
            assert Files.entries()["ECM_MRG12_Slave.sil"]["files"]==["a.dcm"]
            Files.update("ECM_MRG12_Slave.sil",["new.dcm"])
            write.assert_called_once_with("slave","parameters",{"Parameter_files":"-Pnew.dcm","Other":"keep"},session="setup-control")
            assert props["slave"]["parameters"]["Parameter_files"]=="-Pa.dcm"

    @classmethod
    def test_missing_sfu_does_not_write(cls):
        import pytest
        with patch.object(Silver,"get_top_level_sfu_uuids",return_value=[]),patch.object(Silver,"set_sfu_property") as write:
            with pytest.raises(RuntimeError):Files.update("ECM_MRG12_Master.sil",[])
            write.assert_not_called()

    @classmethod
    def test_apply_saves_then_reloads(cls):
        events=[]
        with patch.object(Silver,"stop",side_effect=lambda **kw:events.append("stop")),patch.object(Silver,"open",side_effect=lambda *a,**kw:events.append("open")),patch.object(Files,"update_many",side_effect=lambda changes:events.append("update")),patch.object(Silver,"save",side_effect=lambda *args,**kw:events.append("save")),patch.object(Silver,"reload",side_effect=lambda **kw:events.append("reload")):
            Files.apply_via_api({"ECM_MRG12_Slave.sil":["one.dcm"]},"setup.sil")
        assert events==["stop","update","save","reload","save"]

    @classmethod
    def test_panel_grouped_row_updates_other_sfu_and_appends_blank(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from PySide6.QtWidgets import QApplication,QWidget
        from source.setup_operation.parameter_files_panel import ParameterFilesPanel as Panel
        app=QApplication.instance() or QApplication([]);owner=QWidget();sent=[]
        panel=Panel.create(owner,lambda action,data:sent.append((action,data)))
        slave,master=Files.TARGETS
        Panel.populate(panel,{slave:{"files":["slave.dcm"]},master:{"files":["master.dcm"]}})
        assert not panel._grouped.isChecked()
        Panel.change(panel,slave,1,"extra.dcm")
        assert not sent
        assert len(panel._sections[slave]["edits"])==3
        assert panel._sections[slave]["edits"][-1].text()==""
        panel._grouped.setChecked(True)
        Panel.change(panel,master,0,"shared.DCM")
        assert not sent
        assert panel._sections[master]["edits"][0].text()=="shared.DCM"
        assert panel._sections[slave]["edits"][0].text()=="shared.DCM"
        Panel.apply(panel,master)
        assert sent[-1][0]=="parameters_save" and set(sent[-1][1])=={slave,master}
        panel.close();owner.close()

    @classmethod
    def test_default_browser_directory_is_specific_to_sfu(cls):
        import os,tempfile
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from pathlib import Path
        from PySide6.QtWidgets import QApplication,QWidget
        from source.setup_operation.parameter_files_panel import ParameterFilesPanel as Panel
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            slave_folder=root/"ECM"/"Slave"/"Config"/"Datenstand";slave_folder.mkdir(parents=True)
            master_folder=root/"ECM"/"Master"/"GeneralConfig"/"Datenstand";master_folder.mkdir(parents=True)
            owner=QWidget();owner._setup_control={"selected":str(root/"Setup.sil")}
            panel=Panel.create(owner,lambda *args:None)
            slave,master=Files.TARGETS
            Panel.populate(panel,{slave:{"path":"ECM/Slave/"+slave,"files":[]},master:{"path":"ECM/Master/"+master,"files":[]}})
            assert Panel.default_directory(panel,slave)==slave_folder
            assert Panel.default_directory(panel,master)==master_folder
            panel.close();owner.close()

    @classmethod
    def test_paths_inside_active_simfiles_are_relative_outside_absolute(cls):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"SimFiles";root.mkdir()
            setup=root/"Setup.sil"
            inside=root/"ECM"/"Config"/"Datenstand"/"file.DCM"
            outside=Path(directory)/"Other"/"file.dcm"
            assert Files.display_path(str(inside),setup)=="ECM/Config/Datenstand/file.DCM"
            assert Files.display_path(str(outside),setup)==outside.resolve().as_posix()
            assert Files.display_path("ECM/Config/Datenstand/file.DCM",setup)=="ECM/Config/Datenstand/file.DCM"
            assert Files.display_path("../Other/file.dcm",setup)==outside.resolve().as_posix()
            similar=Path(directory)/"SimFiles_other"/"file.dcm"
            assert Files.display_path(str(similar),setup)==similar.resolve().as_posix()

    @classmethod
    def test_remove_is_staged_until_apply_and_keeps_empty_row(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from PySide6.QtWidgets import QApplication,QWidget
        from source.setup_operation.parameter_files_panel import ParameterFilesPanel as Panel
        app=QApplication.instance() or QApplication([]);owner=QWidget();sent=[]
        panel=Panel.create(owner,lambda action,data:sent.append((action,data)))
        slave,master=Files.TARGETS
        Panel.populate(panel,{slave:{"files":["main.dcm","extra.dcm"]},master:{"files":["main.dcm","extra.dcm"]}})
        panel._grouped.setChecked(True)
        panel._sections[slave]["edits"][1].parentWidget()._remove.click()
        assert not sent
        for name in (slave,master):
            assert Panel.values(panel,name)==["main.dcm"]
            assert len(panel._sections[name]["edits"])==2
            assert not panel._sections[name]["edits"][-1].parentWidget()._remove.isVisible()
        Panel.apply(panel,slave)
        assert sent==[("parameters_save",{slave:["main.dcm"],master:["main.dcm"]})]
        panel.close();owner.close()

    @classmethod
    def test_ungrouped_apply_writes_both_changed_sides(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from PySide6.QtWidgets import QApplication,QWidget
        from source.setup_operation.parameter_files_panel import ParameterFilesPanel as Panel
        app=QApplication.instance() or QApplication([]);owner=QWidget();sent=[]
        panel=Panel.create(owner,lambda *args:sent.append(args));slave,master=Files.TARGETS
        Panel.populate(panel,{slave:{"files":["s.dcm","x.dcm","y.dcm"]},master:{"files":["m.dcm","x.dcm","y.dcm"]}})
        panel._grouped.setChecked(True)
        Panel.remove(panel,master,1)
        assert Panel.values(panel,slave)==["s.dcm","y.dcm"]
        assert Panel.values(panel,master)==["m.dcm","y.dcm"]
        panel._grouped.setChecked(False);Panel.apply(panel,slave)
        assert set(sent[-1][1])=={slave,master}
        panel.close();owner.close()

    @classmethod
    def test_display_path_does_not_touch_filesystem_or_silver(cls):
        from pathlib import Path
        with patch.object(Path,"resolve",side_effect=AssertionError("filesystem access")),patch.object(Path,"stat",side_effect=AssertionError("filesystem access")),patch.object(Silver,"set_sfu_property") as write:
            assert Files.display_path("C:/SimFiles/ECM/a.dcm","C:/SimFiles/setup.sil")=="ECM/a.dcm"
            assert Files.display_path("//server/share/other.dcm","C:/SimFiles/setup.sil")=="//server/share/other.dcm"
            write.assert_not_called()

    @classmethod
    def test_main_dcm_slot_remains_and_replacement_is_first(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from PySide6.QtWidgets import QApplication,QWidget
        from source.setup_operation.parameter_files_panel import ParameterFilesPanel as Panel
        app=QApplication.instance() or QApplication([]);owner=QWidget();sent=[]
        panel=Panel.create(owner,lambda *args:sent.append(args));slave,master=Files.TARGETS
        Panel.populate(panel,{slave:{"files":["main.dcm","extra.dcm"]},master:{"files":["main.dcm","extra.dcm"]}})
        panel._grouped.setChecked(True);Panel.remove(panel,slave,0)
        for name in (slave,master):
            edits=panel._sections[name]["edits"]
            assert edits[0].text()=="" and edits[0].placeholderText()=="Haupt-DCM-Datei laden"
            assert edits[1].text()=="extra.dcm"
        assert not sent
        with patch("source.setup_operation.parameter_files_panel.Dialogs.message") as message:
            Panel.apply(panel,slave)
            message.assert_called_once()
        assert not sent
        Panel.change(panel,slave,0,"replacement.dcm");Panel.apply(panel,slave)
        assert sent[-1][1]=={slave:["replacement.dcm","extra.dcm"],master:["replacement.dcm","extra.dcm"]}
        panel.close();owner.close()

    @classmethod
    def test_disconnected_panel_shows_dash_instead_of_load_prompt(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from PySide6.QtWidgets import QApplication,QWidget
        from source.setup_operation.parameter_files_panel import ParameterFilesPanel as Panel
        app=QApplication.instance() or QApplication([]);owner=QWidget()
        panel=Panel.create(owner,lambda *args:None)
        for section in panel._sections.values():
            assert section["edits"][0].placeholderText()=="—"
            assert not section["edits"][0].isEnabled()
        slave=Files.TARGETS[0];Panel.populate(panel,{slave:{"files":[]}})
        assert panel._sections[slave]["edits"][0].placeholderText()=="Haupt-DCM-Datei laden"
        panel.close();owner.close()

    @classmethod
    def test_grouped_aed_and_dcm_share_one_apply(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from PySide6.QtWidgets import QApplication,QWidget
        from source.setup_operation.parameter_files_panel import ParameterFilesPanel as Panel
        app=QApplication.instance() or QApplication([]);owner=QWidget();sent=[]
        panel=Panel.create(owner,lambda *args:sent.append(args));slave,master=Files.TARGETS
        Panel.populate(panel,{slave:{"files":["s.dcm"],"variant":"old_s.aed"},master:{"files":["m.dcm"],"variant":"old_m.aed"}})
        panel._grouped.setChecked(True);Panel.change_variant(panel,master,"new.AED")
        assert not sent
        assert all(panel._sections[name]["variant"].text()=="new.AED" for name in (slave,master))
        Panel.apply(panel,slave)
        assert sent==[("parameters_save",{slave:{"files":["s.dcm"],"variant":"new.AED"},master:{"files":["m.dcm"],"variant":"new.AED"}})]
        panel.close();owner.close()

    @classmethod
    def test_api_updates_aed_and_dcm_preserving_other_parameters(cls):
        props={"path":"ECM/ECM_MRG12_Slave.sil","parameters":{"Parameter_files":"-Pold.dcm","variant_code_string_file":"old.aed","Other":"keep"}}
        with patch.object(Silver,"get_top_level_sfu_uuids",return_value=["slave"]),patch.object(Silver,"get_sfu_properties",return_value=props),patch.object(Silver,"set_sfu_property",return_value=True) as write:
            Files.update_many({"ECM_MRG12_Slave.sil":{"files":["new.dcm"],"variant":"new.aed"}})
            assert write.call_args.args[2]=={"Parameter_files":"-Pnew.dcm","variant_code_string_file":"new.aed","Other":"keep"}

    @classmethod
    def test_many_slave_dcms_do_not_push_master_down(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from PySide6.QtWidgets import QApplication,QWidget
        from source.setup_operation.parameter_files_panel import ParameterFilesPanel as Panel
        app=QApplication.instance() or QApplication([]);owner=QWidget()
        panel=Panel.create(owner,lambda *args:None);panel.resize(1000,900);panel.show()
        slave,master=Files.TARGETS
        Panel.populate(panel,{slave:{"files":["main.dcm","second.dcm","third.dcm"]},master:{"files":["main.dcm","second.dcm","third.dcm"]}})
        app.processEvents();Panel.fit_lists(panel);app.processEvents()
        original_height=panel._sections[slave]["scroll"].height()
        master_y=panel._sections[master]["scroll"].mapTo(panel.widget(),__import__('PySide6.QtCore',fromlist=['QPoint']).QPoint()).y()
        Panel.populate(panel,{slave:{"files":[f"file{i}.dcm" for i in range(20)]},master:{"files":["main.dcm","second.dcm","third.dcm"]}})
        app.processEvents()
        assert panel._sections[slave]["scroll"].height()==original_height
        assert abs(panel._sections[slave]["scroll"].height()-panel._sections[master]["scroll"].height())<=1
        panel.setEnabled(False);Panel.fit_lists(panel);app.processEvents()
        assert panel._sections[slave]["scroll"].height()==original_height
        panel.setEnabled(True)
        assert panel._sections[slave]["scroll"].verticalScrollBar().maximum()>0
        assert panel._sections[master]["scroll"].mapTo(panel.widget(),__import__('PySide6.QtCore',fromlist=['QPoint']).QPoint()).y()==master_y
        panel.close();owner.close()

    @classmethod
    def test_file_selection_shows_wait_before_staging_and_does_not_flash(cls):
        from unittest.mock import Mock
        from PySide6.QtWidgets import QApplication,QWidget,QDialog,QLabel
        from PySide6.QtTest import QTest
        from source.setup_operation.parameter_files_panel import ParameterFilesPanel as Panel
        from source.silEinrichten import SilEinrichten
        app=QApplication.instance() or QApplication([]);owner=QWidget();sent=[]
        panel=Panel.create(owner,lambda *args:sent.append(args));slave,master=Files.TARGETS
        Panel.populate(panel,{slave:{"files":["old.dcm"],"variant":"old.aed"},master:{"files":["old.dcm"],"variant":"old.aed"}})
        for extension in ("dcm","aed"):
            progress=QDialog(owner);body=QLabel(progress);animation=Mock()
            callback=(lambda:Panel.change(panel,slave,0,"new.dcm")) if extension=="dcm" else (lambda:Panel.change_variant(panel,slave,"new.aed"))
            with patch.object(SilEinrichten,"create_progress_card",return_value=(progress,body,animation)),patch("source.setup_operation.parameter_files_panel.Dialogs.foreground"):
                Panel.selection_progress(panel,"new."+extension,callback)
                assert progress.isVisible()
                assert not sent
                QTest.qWait(100)
                assert not sent
                animation.stop.assert_called_once()
        assert panel._entries[slave]["files"]==["new.dcm"]
        assert panel._entries[slave]["variant"]=="new.aed"
        panel.close();owner.close()

    @classmethod
    def test_default_flash_route_is_restored_to_api(cls):
        from source.silver.xml_flash import SilverXmlFlash as Xml
        assert Files.XML_FLASH_TRIAL is False
        with patch.object(Files,"apply_via_api",return_value="api") as api,patch.object(Xml,"prepare") as xml:
            assert Files.apply_and_reload({},"setup.sil")=="api"
            api.assert_called_once_with({},"setup.sil",None)
            xml.assert_not_called()
