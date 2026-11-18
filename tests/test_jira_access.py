import unittest
from source.stand_management.jira_access import JiraAccess

class JiraAccessTests(unittest.TestCase):
    USER={"status":200,"json":True,"authenticated":True}
    BOARD={"status":200,"json":True,"id":45869,"type":"kanban","named":True,"project":"DEVOTTOSIL"}
    @classmethod
    def test_exact_board_links(cls):
        assert len(JiraAccess.BOARD_IDS)==4
        assert JiraAccess.url("Allgemein").endswith("/boards/45869")
        assert JiraAccess.url("Testing-Grundmotor").endswith("/boards/48241")
        assert JiraAccess.url("Testing-OBD").endswith("/boards/48242")
        assert JiraAccess.url("Testing-Sensorik").endswith("/boards/48243")
    @classmethod
    def test_login_and_joining_are_not_permission_denials(cls):
        assert JiraAccess.page_state("https://id.atlassian.com/login","")=="login_required"
        assert JiraAccess.page_state("https://mercedes-benz.atlassian.net/", "Sie treten Jira bei. Bitte warten Sie einen Moment.")=="joining"
        assert JiraAccess.classify(45869,"joining",cls.USER,cls.BOARD)=="joining"
        assert JiraAccess.classify(45869,"login_required",cls.USER,{"status":403,"json":True,"jira_error":True})=="login_required"
    @classmethod
    def test_authenticated_json_denial_is_required(cls):
        assert JiraAccess.classify(45869,"unknown",cls.USER,{"status":403,"json":True,"jira_error":True})=="denied"
        assert JiraAccess.classify(45869,"unknown",{}, {"status":403,"json":True,"jira_error":True})=="unknown"
        assert JiraAccess.classify(45869,"unknown",cls.USER,{"status":403,"json":False})=="unknown"
    @classmethod
    def test_404_cannot_distinguish_deleted_from_missing_permission(cls):
        assert JiraAccess.classify(45869,"unknown",cls.USER,{"status":404,"json":True,"jira_error":True})=="not_visible_or_missing"
    @classmethod
    def test_positive_requires_exact_board_id_and_authenticated_session(cls):
        assert JiraAccess.classify(45869,"unknown",cls.USER,cls.BOARD)=="allowed"
        assert JiraAccess.classify(48241,"unknown",cls.USER,cls.BOARD)=="unknown"
        assert JiraAccess.classify(45869,"unknown",{},cls.BOARD)=="unknown"
        assert JiraAccess.classify(45869,"unknown",cls.USER,{**cls.BOARD,"private":True})=="unknown"
    @classmethod
    def test_technical_failure_and_expired_login_not_denied(cls):
        assert JiraAccess.classify(45869,"unknown",cls.USER,{"status":401})=="login_required"
        assert JiraAccess.classify(45869,"unknown",cls.USER,{"status":429})=="rate_limited"
        assert JiraAccess.classify(45869,"unknown",cls.USER,{"status":503})=="service_error"
        assert JiraAccess.classify(45869,"unknown",cls.USER,{"status":0})=="unknown"

    @classmethod
    def test_proxy_json_error_is_not_reported_as_jira_permission_denial(cls):
        assert JiraAccess.classify(45869,"unknown",cls.USER,{"status":403,"json":True})=="unknown"

    @classmethod
    def test_partial_private_or_wrong_project_board_is_not_positive(cls):
        assert JiraAccess.classify(45869,"unknown",cls.USER,{**cls.BOARD,"named":False})=="unknown"
        assert JiraAccess.classify(45869,"unknown",cls.USER,{**cls.BOARD,"project":"OTHER"})=="unknown"

    @classmethod
    def test_selector_has_five_actions_with_correct_routes(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        from unittest.mock import patch
        from source.stand_management.jira import JiraTool
        app=QApplication.instance() or QApplication([])
        with patch.object(JiraTool,"navigate") as navigate,patch.object(JiraTool,"request_access") as request:
            QTimer.singleShot(20,cls.click_selector_buttons)
            JiraTool.open()
            assert [call.args[0] for call in navigate.call_args_list]==list(JiraAccess.BOARD_IDS)
            request.assert_called_once()
            assert cls._buttons==[*JiraAccess.BOARD_IDS,"Jira-Zugriff beantragen"]

    @classmethod
    def click_selector_buttons(cls):
        from PySide6.QtWidgets import QApplication,QPushButton
        dialog=QApplication.activeModalWidget()
        try:
            buttons=dialog.findChildren(QPushButton)
            cls._buttons=[button.text() for button in buttons]
            for button in buttons:button.click()
        finally:dialog.reject()

    @classmethod
    def test_login_page_does_not_trigger_board_api_requests(cls):
        from unittest.mock import Mock
        driver=Mock();driver.current_url="https://id.atlassian.com/login"
        driver.find_element.return_value.text="Einloggen, um fortzufahren"
        assert JiraAccess.snapshot(driver,45869)=="login_required"
        driver.execute_async_script.assert_not_called()

    @classmethod
    def test_reported_join_url_is_access_pending_not_login_or_denied(cls):
        from urllib.parse import urlencode
        query=urlencode({"resource":"ari:cloud:jira::site/"+JiraAccess.SITE_ID,"continue":JiraAccess.url("Allgemein")+"?isEligibleForUserSurvey=true"})
        url="https://id.atlassian.com/join/user-access?"+query
        state=JiraAccess.page_state(url,"Sie treten Jira bei. Bitte warten Sie einen Moment.")
        assert state=="site_access_pending"
        assert JiraAccess.classify(45869,state,None,None)=="site_access_pending"
        from unittest.mock import Mock
        driver=Mock();driver.current_url=url;driver.find_element.return_value.text="Sie treten Jira bei."
        assert JiraAccess.snapshot(driver,45869)=="site_access_pending"
        driver.execute_async_script.assert_not_called()

    @classmethod
    def test_join_flow_for_other_site_does_not_count_as_target_access_pending(cls):
        from urllib.parse import urlencode
        for resource,destination in (("ari:cloud:jira::site/OTHER",JiraAccess.url("Allgemein")),("ari:cloud:jira::site/"+JiraAccess.SITE_ID,"https://other.atlassian.net/jira/software/c/projects/DEVOTTOSIL/boards/45869")):
            url="https://id.atlassian.com/join/user-access?"+urlencode({"resource":resource,"continue":destination})
            assert JiraAccess.page_state(url,"")!="site_access_pending"

    @classmethod
    def test_actual_mercedes_login_is_recognized(cls):
        assert JiraAccess.page_state("https://login.mercedes-benz.com/","Mit Passwort")=="login_required"
