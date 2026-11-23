import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from unittest.mock import patch
import pytest
from PySide6.QtWidgets import QApplication,QWidget,QPushButton
from source.setup_operation.parameter_files_panel import ParameterFilesPanel as Panel
from source.silver.parameter_files import SilverParameterFiles as Files
from source.silver.operation import SilverOperation as Op


def panel():
    app=QApplication.instance() or QApplication([]);owner=QWidget();sent=[]
    view=Panel.create(owner,lambda *args:sent.append(args));view._grouped.setChecked(False);slave,master=Files.TARGETS
    Panel.populate(view,{slave:{"files":["s.dcm"],"variant":"s.aed"},master:{"files":["m.dcm"],"variant":"m.aed"}})
    return app,owner,view,sent,slave,master


def test_single_flash_button_targets_only_modified_side():
    app,owner,view,sent,slave,master=panel()
    try:
        assert len([b for b in view.findChildren(QPushButton) if b.text()=="Flashen"])==1
        assert not [b for b in view.findChildren(QPushButton) if b.text()=="Übernehmen"]
        Panel.change(view,master,0,"new.dcm");view._flash.click()
        assert set(sent[-1][1])=={master}
        assert sent[-1][1][master]["files"]==["new.dcm"]
    finally:view.deleteLater();owner.deleteLater();app.processEvents()


def test_enabling_group_after_aed_edit_mirrors_change_without_replacing_other_dcms():
    app,owner,view,sent,slave,master=panel()
    try:
        Panel.change_variant(view,slave,"new.aed");view._grouped.setChecked(True)
        assert view._sections[master]["variant"].text()=="new.aed"
        assert not sent
        view._flash.click()
        result=sent[-1][1]
        assert set(result)=={slave,master}
        assert result[master]["variant"]==result[slave]["variant"]=="new.aed"
        assert result[master]["files"]==["m.dcm"]
    finally:view.deleteLater();owner.deleteLater();app.processEvents()


@pytest.mark.parametrize("key",["accelerator","brake"])
def test_pedal_boundaries_are_written_without_conversion(key):
    with patch.object(Op,"write") as write:
        for value in (0,0.2,50,100):
            Op.set_input(key,value)
            assert write.call_args.args[1]==value
        write.reset_mock()
        for value in (-0.1,100.01,float("inf"),float("nan")):
            with pytest.raises(ValueError):Op.set_input(key,value)
        write.assert_not_called()


@pytest.mark.parametrize("side",[0,1])
def test_pending_dcm_change_is_visible_on_other_side_as_soon_as_grouping_is_enabled(side):
    app,owner,view,sent,slave,master=panel()
    source,other=(slave,master) if side==0 else (master,slave)
    try:
        Panel.change(view,source,0,"shared.dcm")
        assert Panel.values(view,other)!=["shared.dcm"]
        view._grouped.setChecked(True)
        assert Panel.values(view,source)==Panel.values(view,other)==["shared.dcm"]
        assert not sent
        view._flash.click()
        assert set(sent[-1][1])=={slave,master}
        assert all(entry["files"]==["shared.dcm"] for entry in sent[-1][1].values())
    finally:view.deleteLater();owner.deleteLater();app.processEvents()


def test_grouping_does_not_duplicate_pending_added_row_on_flash_or_repeated_toggle():
    app,owner,view,sent,slave,master=panel()
    try:
        Panel.change(view,master,1,"extra.dcm")
        for _ in range(2):
            view._grouped.setChecked(True)
            assert Panel.values(view,slave)==["s.dcm","extra.dcm"]
            view._grouped.setChecked(False)
        view._grouped.setChecked(True);view._flash.click()
        assert sent[-1][1][slave]["files"]==["s.dcm","extra.dcm"]
        assert sent[-1][1][master]["files"]==["m.dcm","extra.dcm"]
    finally:view.deleteLater();owner.deleteLater();app.processEvents()


def test_late_grouping_does_not_add_a_file_already_present_at_that_position():
    app,owner,view,sent,slave,master=panel()
    try:
        Panel.populate(view,{slave:{"files":["s.dcm","extra.dcm"]},master:{"files":["m.dcm"]}})
        Panel.change(view,master,1,"extra.dcm")
        view._grouped.setChecked(True);view._flash.click()
        assert sent[-1][1][slave]==["s.dcm","extra.dcm"]
    finally:view.deleteLater();owner.deleteLater();app.processEvents()



def test_new_panel_groups_both_flash_targets_by_default():
    app=QApplication.instance() or QApplication([]);owner=QWidget();sent=[]
    view=Panel.create(owner,lambda *args:sent.append(args));slave,master=Files.TARGETS
    try:
        assert view._grouped.isChecked()
        Panel.populate(view,{slave:{"files":["s.dcm"]},master:{"files":["m.dcm"]}})
        Panel.change(view,master,0,"shared.dcm");view._flash.click()
        assert set(sent[-1][1])=={slave,master}
        assert sent[-1][1][slave]==sent[-1][1][master]==["shared.dcm"]
    finally:view.deleteLater();owner.deleteLater();app.processEvents()
