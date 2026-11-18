import json
from pathlib import Path
from unittest.mock import patch
import pytest
from tools.package_runtime import RuntimePackage
from source.core.driver_archive import DriverArchive
from source.core.runtime import Runtime


def test_driver_packaging_keeps_every_offline_version_and_roundtrips(tmp_path):
    source=tmp_path/"source";destination=tmp_path/"distribution";cache=tmp_path/"cache"
    versions=["148.0.1.2","152.0.3.4"]
    source.mkdir();(source/"manifest.json").write_text(json.dumps({"versions":versions}))
    for version in versions:
        folder=source/version;folder.mkdir();(folder/"msedgedriver.exe").write_bytes(b"MZ"+b"driver"*10000)
        (folder/"LICENSE").write_text("licence")
    result=RuntimePackage.package_drivers(source,destination)
    assert result["saved_bytes"]>0
    with patch.object(Runtime,"data_root",return_value=cache):
        for version in versions:
            archive=destination/version/"edgedriver.zip"
            executable=DriverArchive.unpack(archive)
            assert executable.read_bytes()==(source/version/"msedgedriver.exe").read_bytes()
            assert not (destination/version/"msedgedriver.exe").exists()
            assert (destination/version/"LICENSE").read_text()=="licence"
            before=executable.stat().st_mtime_ns
            assert DriverArchive.unpack(archive)==executable
            assert executable.stat().st_mtime_ns==before


def test_corrupt_driver_is_rejected_without_overwriting_cache(tmp_path):
    import zipfile
    root=tmp_path/"package";folder=root/"152.0.1.2";folder.mkdir(parents=True)
    (root/"manifest.json").write_text(json.dumps({"versions":[folder.name],"sha256":{folder.name:"0"*64}}))
    archive=folder/"edgedriver.zip"
    with zipfile.ZipFile(archive,"w") as package:package.writestr("msedgedriver.exe",b"MZwrong")
    with patch.object(Runtime,"data_root",return_value=tmp_path/"cache"):
        with pytest.raises(ValueError,match="beschädigt"):DriverArchive.unpack(archive)
    assert not (tmp_path/"cache/drivers"/folder.name/"msedgedriver.exe").exists()


def test_browser_uses_matching_offline_archive_without_manager(tmp_path):
    from source.silEinrichten import SilEinrichten
    from unittest.mock import Mock
    folder=tmp_path/"drivers/152.0.3.4";folder.mkdir(parents=True)
    archive=folder/"edgedriver.zip";archive.write_bytes(b"fixture")
    cache=tmp_path/"cache/msedgedriver.exe";cache.parent.mkdir();cache.write_bytes(b"MZ")
    options=Mock()
    with patch.object(Runtime,"project_root",return_value=tmp_path),patch.object(SilEinrichten,"installed_edge_version",return_value="152.0.3.99"),patch.object(DriverArchive,"unpack",return_value=cache) as unpack,patch("source.silEinrichten.Service") as service,patch("source.silEinrichten.webdriver.Edge") as browser:
        assert SilEinrichten.create_edge_driver(options)==browser.return_value
        unpack.assert_called_once_with(archive)
        service.assert_called_once_with(executable_path=str(cache))
        browser.assert_called_once_with(service=service.return_value,options=options)
