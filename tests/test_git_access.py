import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from source.stand_management.git import GitTool

class GitAccessTests(unittest.TestCase):
    @classmethod
    def test_no_token_never_requests_network(cls):
        with patch.object(GitTool, "windows_user", return_value={"username":"OGENCUE"}), patch.object(GitTool, "api_get") as request:
            result = GitTool.check_access()
            assert result["status"] == "authentication_required"
            assert result["account_access"] is None
            request.assert_not_called()

    @classmethod
    def test_authenticated_identity_is_not_guessed_from_windows(cls):
        with patch.object(GitTool, "windows_user", return_value={"username":"OGENCUE"}), patch.object(GitTool, "api_get", side_effect=[{"login":"different_login"},{"full_name":"devM286/SimFiles"}]):
            result = GitTool.check_access("test-token")
            assert result["github_user"] == "different_login"
            assert result["repository_access"] is True

    @classmethod
    def test_uncertain_http_errors_do_not_claim_missing_rights(cls):
        for code in (401,403,404,500):
            with patch.object(GitTool, "windows_user", return_value={}), patch.object(GitTool, "api_get", side_effect=HTTPError("https://example.invalid",code,"",{},None)):
                result = GitTool.check_access("test-token")
                assert result["account_access"] is None and result["repository_access"] is None
                assert result["http_status"] == code

    @classmethod
    def test_repository_failure_preserves_confirmed_account(cls):
        with patch.object(GitTool, "windows_user", return_value={}), patch.object(GitTool, "api_get", side_effect=[{"login":"user"}, URLError("offline")]):
            result = GitTool.check_access("test-token")
            assert result["account_access"] is True
            assert result["repository_access"] is None
            assert result["status"] == "network_error"
