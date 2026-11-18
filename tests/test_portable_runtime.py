import unittest
from unittest.mock import Mock,patch
from source.core.smoke import SmokeTest

class PortableRuntimeTests(unittest.TestCase):
    @classmethod
    def test_compiled_workers_and_runtime_stay_inside_distribution(cls):
        mappings=[Mock(path="C:/Package/python313.dll"),Mock(path="C:/Package/PySide6/Qt6Core.dll")]
        with patch("sys.frozen",True,create=True),patch("sys.executable","C:/Package/siLAssistent.exe"),patch("psutil.Process") as process:
            process.return_value.memory_maps.return_value=mappings
            result=SmokeTest.portable_runtime_check()
            assert result["packaged"] and result["bundled_runtime"] and result["self_contained_workers"]

    @classmethod
    def test_external_runtime_is_rejected(cls):
        mappings=[Mock(path="C:/ExternalPython/python313.dll")]
        with patch("sys.frozen",True,create=True),patch("sys.executable","C:/Package/siLAssistent.exe"),patch("psutil.Process") as process:
            process.return_value.memory_maps.return_value=mappings
            with unittest.TestCase().assertRaisesRegex(AssertionError,"outside distribution"):
                SmokeTest.portable_runtime_check()


def test_packaged_silver_worker_restarts_same_exe_without_vendor_python():
    from source.silver.connection import SilverConnection
    with patch("sys.frozen",True,create=True),patch("sys.executable","C:/Package/siLAssistent.exe"):
        assert SilverConnection.worker_launch_command("C:/Silver")==["C:/Package/siLAssistent.exe","--silver-api-worker","C:/Silver"]
