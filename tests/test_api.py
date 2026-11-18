import ast
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor
from source.inca import Inca, IncaMethods
from source.silver import Silver, SilverSetup
from source.core.catalog import Catalog
from source.core.errors import ConnectionError, ApiCallError, ThreadAffinityError

class ApiTests(unittest.TestCase):
    @classmethod
    def raises(cls, exception):
        return unittest.TestCase().assertRaises(exception)

    @classmethod
    def tearDown(cls):
        Inca._sessions.clear()
        Silver._sessions.clear()

    @classmethod
    def test_inca_connection_is_explicit(cls):
        with cls.raises(ConnectionError):
            Inca.application()
        app = Mock()
        Inca.connect(application=app)
        assert Inca.application() is app
        with cls.raises(ConnectionError):
            Inca.connect(application=app)
        Inca.disconnect()
        app.DisconnectFromTool.assert_called_once()

    @classmethod
    def test_thread_affinity(cls):
        Inca.connect(application=Mock())
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(Inca.application)
            with cls.raises(ThreadAffinityError):
                future.result()

    @classmethod
    def test_inca_errors_keep_cause(cls):
        app = Mock(); app.GetCurrentDataBase.side_effect = ValueError("device error")
        Inca.connect(application=app)
        try:
            Inca.database()
        except ApiCallError as error:
            assert isinstance(error.__cause__, ValueError)
        else:
            raise AssertionError("Vendor failure swallowed")

    @classmethod
    def test_inca_calibration_types_preserved(cls):
        app = Mock(); experiment = Mock(); data = experiment.GetCalibrationElement.return_value.GetValue.return_value
        data.GetDoublePhysValue.return_value = ((1.0, 2.0), (3.0, 4.0))
        Inca.connect(application=app)
        assert Inca.read_calibration(experiment, "map") == ((1.0, 2.0), (3.0, 4.0))
        data.SetDoublePhysValue.return_value = False
        with cls.raises(ApiCallError):
            Inca.write_calibration(experiment, "map", ((9.0,),))

    @classmethod
    def test_all_inca_documented_members_forward(cls):
        app = Mock(); Inca.connect(application=app)
        for name in {record["name"] for record in Catalog.load("inca")["methods"]}:
            getattr(app, name).return_value = name
            assert getattr(IncaMethods, name)(app, 123) == name
            getattr(app, name).assert_called_once_with(123)

    @classmethod
    def test_silver_session_isolation(cls):
        one = Mock(); two = Mock()
        Silver.attach(one, "one"); Silver.attach(two, "two")
        Silver.set_variable_value("speed", 42, session="one")
        one.set_variable_value.assert_called_once_with("speed", 42)
        two.set_variable_value.assert_not_called()
        Silver.close("one")
        assert "two" in Silver._sessions and "one" not in Silver._sessions

    @classmethod
    def test_silver_start_constructor_options(cls):
        backend = Mock(); backend.silverStartedSuccessfully.return_value = True
        factory = Mock(return_value=backend)
        Silver.start("test.sil", gui=False, stopped=True, factory=factory)
        assert factory.call_args.kwargs["args"] == []
        assert factory.call_args.kwargs["gui"] is False
        assert factory.call_args.kwargs["stopped"] is True
        with cls.raises(ConnectionError):
            Silver.start(factory=factory)

    @classmethod
    def test_legacy_silver_version_rejected_clearly(cls):
        # Legacy factory is deliberately a standard-library mock with a signature.
        factory = Mock(); factory.__signature__ = __import__('inspect').Signature([
            __import__('inspect').Parameter("sil", __import__('inspect').Parameter.POSITIONAL_OR_KEYWORD)])
        with cls.raises(ConnectionError):
            Silver.start(version=3, factory=factory)

    @classmethod
    def test_persistent_variable_release_is_none(cls):
        backend = Mock(); Silver.attach(backend)
        Silver.set_variable_value("speed", None)
        backend.set_variable_value.assert_called_once_with("speed", None)

    @classmethod
    def test_setup_snapshot_uses_documented_queries(cls):
        backend = Mock(); backend.get_module_uuids.return_value = ["module"]
        backend.get_top_level_sfu_uuids.return_value = []
        backend.get_project_properties.return_value = {"title": "demo"}
        Silver.attach(backend)
        snapshot = SilverSetup.snapshot()
        assert snapshot["project"] == {"title": "demo"}
        assert set(snapshot["modules"]) == {"module"}

    @classmethod
    def test_source_methods_are_classmethods(cls):
        source = Path(__file__).resolve().parents[1] / "source"
        for path in source.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            # Local callback functions are not methods; inspect class members directly.
            for owner in (node for node in ast.walk(tree) if isinstance(node,ast.ClassDef)):
                for node in owner.body:
                    if isinstance(node,ast.FunctionDef):
                        assert any(isinstance(d,ast.Name) and d.id=="classmethod" for d in node.decorator_list), (path,node.name)
                        assert node.args.args[0].arg=="cls", (path,node.name)
