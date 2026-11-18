class AssistantError(RuntimeError):
    """Base error for automation and deployment."""

class ConnectionError(AssistantError):
    """An automation session is unavailable."""

class ApiCallError(AssistantError):
    """A vendor API call failed; its original exception is preserved."""

class ThreadAffinityError(AssistantError):
    """A session was accessed from a thread other than its owner."""

class RepoAccessRequired(AssistantError):
    """The Git operation requires verified access to the setup repository."""

class GitMissing(AssistantError):
    """Git was removed or its executable no longer exists."""
