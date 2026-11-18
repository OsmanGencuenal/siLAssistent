from source.core.config import Config
from tools.sync_update_ini import UpdateIniSync
import pytest


def test_lw_sync_copies_exact_bytes_and_preserves_backup(tmp_path):
    local=tmp_path/"local.ini";remote=tmp_path/"remote.ini"
    Config.export_installation_config(local)
    parser=Config.parser(local);parser["UPDATE"]={"latest_version":"0.1.0","supportMail":"new@example.invalid"};Config.write(local,parser)
    remote.write_text("[UPDATE]\nlatest_version=0.1.0\n",encoding="utf-8");before=remote.read_bytes()
    assert UpdateIniSync.copy(local,remote)
    assert remote.read_bytes()==local.read_bytes()
    assert remote.with_suffix(".ini.siLAssistent.bak").read_bytes()==before
    assert not UpdateIniSync.copy(local,remote)


def test_lw_sync_does_not_erase_published_installer_metadata(tmp_path):
    local=tmp_path/"local.ini";remote=tmp_path/"remote.ini"
    Config.export_installation_config(local)
    remote.write_text("[UPDATE]\ninstaller_path=release.exe\nsha256=published-hash\n",encoding="utf-8");before=remote.read_bytes()
    with pytest.raises(ValueError,match="installer_path"):UpdateIniSync.copy(local,remote)
    assert remote.read_bytes()==before
