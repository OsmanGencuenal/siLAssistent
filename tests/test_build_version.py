from pathlib import Path
from unittest.mock import patch
import pytest
from tools.select_build_version import BuildVersion
from source.core.config import Config


def files(tmp_path):
    root=tmp_path/"project";root.mkdir();(root/"VERSION").write_text("0.1.0\n")
    local=root/"siLAssistent_Update.ini";remote=tmp_path/"LW.ini"
    for path in (local,remote):path.write_text("[UPDATE]\nlatest_version=0.1.0\ninstaller_path=keep.exe\nsha256=keep-hash\n[PATH]\nsilSetupPath=keep-path\n")
    return root,local,remote


def test_confirmed_version_updates_three_files_preserving_other_values(tmp_path):
    root,local,remote=files(tmp_path)
    answers=iter(["J","bad value","1.2.3.4"])
    assert BuildVersion.prompt(root,remote,read=lambda _:next(answers),write=lambda _:None)=="1.2.3.4"
    assert (root/"VERSION").read_text().strip()=="1.2.3.4"
    for path in (local,remote):
        parser=Config.parser(path)
        assert parser.get("UPDATE","latest_version")=="1.2.3.4"
        assert parser.get("UPDATE","installer_path")=="keep.exe"
        assert parser.get("UPDATE","sha256")=="keep-hash"
        assert parser.get("PATH","silSetupPath")=="keep-path"


def test_no_keeps_every_file_unchanged(tmp_path):
    root,local,remote=files(tmp_path);before={p:p.read_bytes() for p in (root/"VERSION",local,remote)}
    assert BuildVersion.prompt(root,remote,read=lambda _:"N",write=lambda _:None)=="0.1.0"
    assert all(path.read_bytes()==data for path,data in before.items())


def test_unavailable_share_does_not_change_local_version(tmp_path):
    root,local,remote=files(tmp_path);remote.unlink();before=local.read_bytes()
    with pytest.raises(FileNotFoundError):BuildVersion.update("1.2.3",root,remote)
    assert local.read_bytes()==before and (root/"VERSION").read_text().strip()=="0.1.0"


def test_failed_write_rolls_back_previous_manifest(tmp_path):
    root,local,remote=files(tmp_path);before={p:p.read_bytes() for p in (root/"VERSION",local,remote)}
    original=Config.write
    def write(path,parser):
        if path==remote:raise OSError("network write failed")
        original(path,parser)
    with patch.object(Config,"write",side_effect=write):
        with pytest.raises(OSError):BuildVersion.update("2.0.0",root,remote)
    assert all(path.read_bytes()==data for path,data in before.items())


@pytest.mark.parametrize("value",["1.2", "1.2.3.4.5", "1.2.65536", "$(bad)", "1.a.2"])
def test_invalid_versions_are_rejected(value):
    with pytest.raises(ValueError):BuildVersion.validate(value)
