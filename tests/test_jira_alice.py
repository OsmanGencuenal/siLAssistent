import unittest
from unittest.mock import Mock,patch
from source.stand_management.jira_alice import JiraAlice
from source.stand_management.jira import JiraTool
from source.core.config import Config

class JiraAliceTests(unittest.TestCase):
    @classmethod
    def test_only_role_field_is_used_not_application_search(cls):
        driver=Mock();driver.current_url=JiraAlice.URL
        app=Mock();app.accessible_name="Suche nach ID, Name oder Beschreibung"
        role=Mock();role.accessible_name=JiraAlice.SEARCH_LABEL
        driver.find_elements.return_value=[app,role]
        assert JiraAlice.role_input(driver) is role

    @classmethod
    def test_search_only_types_query_and_clicks_specific_search_icon(cls):
        field=Mock();field.get_attribute.return_value="devottosil"
        button=Mock();button.is_displayed.return_value=True;button.is_enabled.return_value=True
        field.find_element.return_value.find_elements.return_value=[button]
        JiraAlice.search(field)
        field.clear.assert_called_once_with()
        field.send_keys.assert_called_once_with("devottosil")
        button.click.assert_called_once_with()

    @classmethod
    def test_ambiguous_search_does_not_click_anything(cls):
        field=Mock();field.get_attribute.return_value="devottosil"
        first=Mock();second=Mock()
        field.find_element.return_value.find_elements.return_value=[first,second]
        with unittest.TestCase().assertRaises(RuntimeError):JiraAlice.search(field)
        first.click.assert_not_called();second.click.assert_not_called()

    @classmethod
    def test_prepare_stops_at_role_results_and_does_not_set_user_access_flag(cls):
        driver=Mock();driver.current_url=JiraAlice.URL
        stop=Mock();stop.is_set.return_value=False
        notify=Mock()
        with patch.object(JiraAlice,"role_input",return_value=Mock()),patch.object(JiraAlice,"search") as search,patch.object(JiraAlice,"roles_visible",return_value=True),patch.object(Config,"set_state") as save:
            JiraAlice.prepare(driver,stop,notify)
            driver.get.assert_called_once_with(JiraAlice.URL)
            search.assert_called_once()
            notify.assert_any_call("role_ready")
            save.assert_not_called()
            driver.find_element.assert_not_called()

    @classmethod
    def test_request_buttons_share_same_queue_action(cls):
        with patch.object(JiraTool,"submit") as submit:
            JiraTool.request_access(None)
            submit.assert_called_once_with("Jira-Zugriff beantragen",navigate=True)

    @classmethod
    def test_no_form_editing_on_other_login_host(cls):
        driver=Mock();driver.current_url="https://login.mercedes-benz.com/"
        assert JiraAlice.role_input(driver) is None
        driver.find_elements.assert_not_called()
