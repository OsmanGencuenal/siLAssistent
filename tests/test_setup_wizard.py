from types import SimpleNamespace
import queue
import threading
import unittest
from unittest.mock import Mock, patch
import pywinauto
from pywinauto import uia_defines
from source.silEinrichten import SilverInstallation

class WizardFixture:
    HEADINGS = ["Welcome to the Silver Setup Wizard", "License Agreement", "Select Destination Location",
                "Select Components", "Select Additional Tasks", "Select a destination for the demos",
                "License Configuration", "Ready to Install", "Installing"]

    @classmethod
    def control(cls, name, kind="Text", checked=False, enabled=True):
        control = Mock(spec=["window_text", "is_visible", "is_enabled", "legacy_properties", "select",
                             "selected_text", "get_value", "set_edit_text", "click"])
        control.value = name; control.kind = kind; control.checked = checked
        control.element_info = SimpleNamespace(control_type=kind, element=control)
        control.window_text.side_effect = lambda: control.value
        control.is_visible.return_value = True
        control.is_enabled.return_value = enabled
        control.legacy_properties.side_effect = lambda: {"State": 16 if control.checked else 0}
        control.get_value.side_effect = lambda: control.value
        control.selected_text.side_effect = lambda: control.value
        control.set_edit_text.side_effect = lambda value: setattr(control, "value", value)
        control.select.side_effect = lambda value=None: cls.select(control, value)
        control.click.side_effect = lambda: cls.activate(control)
        return control

    @classmethod
    def select(cls, control, value):
        if control.kind == "ComboBox":
            control.value = value
            for component in cls.components:
                component.checked = True
        else:
            cls.activate(control)

    @classmethod
    def activate(cls, control):
        if control.kind == "Button":
            cls.clicks.append(control.value)
            cls.stage += 1
        elif control.kind == "RadioButton":
            control.checked = True
            if control.value == "For the current user only":
                cls.tasks[1].checked = False
        else:
            control.checked = not control.checked

    @classmethod
    def legacy(cls, element, pattern):
        return SimpleNamespace(DoDefaultAction=lambda: cls.activate(element),
                               CurrentState=16 if element.checked else 0)

    @classmethod
    def descendants(cls, control_type=None):
        extras = {1: [cls.agreement], 2: [cls.destination], 3: [cls.combo, *cls.components],
                  4: cls.tasks, 5: [cls.demo], 6: [cls.server, cls.queuing, cls.warning]}.get(cls.stage, [])
        controls = [cls.control(cls.HEADINGS[cls.stage]), *extras]
        if cls.stage < 8:
            controls.append(cls.control("Install" if cls.stage == 7 else "Next >", "Button"))
        return [c for c in controls if control_type is None or c.kind == control_type]

    @classmethod
    def reset(cls):
        cls.stage = 0; cls.clicks = []
        cls.agreement = cls.control("I accept the agreement", "RadioButton")
        cls.destination = cls.control("DEFAULT_DESTINATION", "Edit")
        cls.demo = cls.control("DEFAULT_DEMO", "Edit")
        cls.components = [cls.control(name, "CheckBox") for name in ("Silver Utility Modules", "Silver Export Tools", "Examples")]
        cls.combo = cls.control("Custom Installation", "ComboBox")
        cls.tasks = [cls.control(name, "RadioButton" if index < 2 else "CheckBox",
                     checked=index in (1, 2, 3, 6), enabled=index not in (2, 3))
                     for index, (name, expected) in enumerate(SilverInstallation.TASK_OPTIONS)]
        cls.server = cls.control("", "Edit")
        cls.queuing = cls.control("Enable license queuing", "CheckBox")
        cls.warning = cls.control("Suppress license expiration warning dialog", "CheckBox", checked=True)
        cls.window = Mock()
        cls.window.exists.return_value = True
        cls.window.descendants.side_effect = cls.descendants
        return cls.window

class SetupWizardTests(unittest.TestCase):
    @classmethod
    def test_complete_ported_sequence_and_exact_checkbox_states(cls):
        window = WizardFixture.reset()
        desktop = Mock(); desktop.window.return_value = window
        events = []
        with patch.object(pywinauto, "Desktop", return_value=desktop), patch.object(uia_defines, "get_elem_interface", side_effect=WizardFixture.legacy), patch.object(SilverInstallation, "show_wizard"), patch.object(SilverInstallation, "save_launch_diagnostic"):
            SilverInstallation.automate_wizard(99, queue.Queue(), threading.Event(), events)
        fixture = WizardFixture
        assert fixture.clicks == ["Next >"] * 7 + ["Install"]
        assert fixture.stage == 8 and fixture.agreement.checked
        assert fixture.destination.value == "DEFAULT_DESTINATION" and fixture.demo.value == "DEFAULT_DEMO"
        assert all(control.checked for control in fixture.components)
        assert all(control.checked == expected for control, (_, expected) in zip(fixture.tasks, SilverInstallation.TASK_OPTIONS))
        assert fixture.server.value == SilverInstallation.license_servers()
        assert fixture.queuing.checked and not fixture.warning.checked
        assert events[-1]["stage"] == "installation_started"
