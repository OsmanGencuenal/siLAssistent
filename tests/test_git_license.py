import unittest
import queue
from unittest.mock import Mock, patch
from source.stand_management.git_license import GitLicense
from source.stand_management.git_window import GitWindow
from source.stand_management.git import GitTool

class GitLicenseTests(unittest.TestCase):
    @classmethod
    def test_billing_values_are_exact(cls):
        assert (GitLicense.OU,GitLicense.COST_CENTER,GitLicense.INTERNAL_ORDER)==("059","3059-0629","305900135547")

    @classmethod
    def test_login_page_is_not_missing_license(cls):
        driver=Mock(current_url="https://login.example.invalid/")
        assert GitLicense.classify(driver)=="unknown"
        driver.find_element.assert_not_called()

    @classmethod
    def test_loaded_text_without_empty_state_is_unknown(cls):
        driver=Mock(current_url=GitLicense.LICENSES)
        driver.find_element.return_value.text="My Workspace\nLicenses"
        assert GitLicense.classify(driver)=="unknown"

    @classmethod
    def test_explicit_empty_state_is_absent(cls):
        driver=Mock(current_url=GitLicense.LICENSES)
        driver.find_element.return_value.text="Licenses\nYou have no licenses"
        assert GitLicense.classify(driver)=="absent"

    @classmethod
    def test_completed_license_is_present(cls):
        driver=Mock(current_url=GitLicense.LICENSES)
        driver.find_element.return_value.text=GitLicense.LICENSE+"\nCompleted"
        driver.find_elements.return_value=[Mock(is_displayed=Mock(return_value=True))]
        assert GitLicense.classify(driver)=="present"

    @classmethod
    def test_failed_repo_check_does_not_run_license_check(cls):
        messages=queue.Queue()
        with patch.object(GitTool,"repository_check",return_value={"allowed":False,"status":"unverified"}), patch.object(GitLicense,"check",return_value={"license":"absent"}) as check:
            GitWindow.worker(messages,"preclone","user",None,1)
            check.assert_not_called()
            assert "license" not in messages.get()[3]

    @classmethod
    def test_other_user_does_not_check_current_users_license(cls):
        messages=queue.Queue()
        with patch.object(GitTool,"repository_check",return_value={"allowed":False,"status":"identity_mismatch"}), patch.object(GitLicense,"check") as check:
            GitWindow.worker(messages,"preclone","other",None,1)
            check.assert_not_called()

    @classmethod
    def test_repo_success_does_not_order_license(cls):
        messages=queue.Queue()
        with patch.object(GitTool,"repository_check",return_value={"allowed":True,"status":"accessible"}), patch.object(GitLicense,"check") as check, patch.object(GitLicense,"prepare_order") as order:
            GitWindow.worker(messages,"check","user",None,1)
            check.assert_not_called()
            order.assert_not_called()

    @classmethod
    def test_missing_label_does_not_enter_billing_values(cls):
        driver=Mock()
        driver.find_elements.return_value=[]
        try:
            GitLicense.fill(driver,"CO -",GitLicense.INTERNAL_ORDER)
            raise AssertionError("Expected failure")
        except RuntimeError:
            pass
        driver.execute_script.assert_not_called()
