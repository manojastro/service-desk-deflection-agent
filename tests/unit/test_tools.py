import pytest

from packages.shared.schemas import Role, UserContext
from services.tools import ToolRegistry
from services.tools.registry import ToolPolicyError


@pytest.fixture()
def employee():
    return UserContext(id="usr_002", username="employee02", display_name="Demo", role=Role.EMPLOYEE, department="Finance")


def test_state_change_requires_confirmation(database, employee):
    tools = ToolRegistry(database)
    with pytest.raises(ToolPolicyError, match="confirmation"):
        tools.execute("unlock_account", {"user_id": employee.id}, employee, "hist_000")


def test_unlock_is_confirmed_and_audited(database, employee):
    tools = ToolRegistry(database)
    assert database.fetchone("SELECT locked FROM mock_accounts WHERE user_id=?", (employee.id,))["locked"] == 1
    result = tools.execute("unlock_account", {"user_id": employee.id}, employee, "hist_000", confirmed=True)
    assert result.success
    assert database.fetchone("SELECT locked FROM mock_accounts WHERE user_id=?", (employee.id,))["locked"] == 0
    assert database.fetchone("SELECT COUNT(*) n FROM tool_executions WHERE session_id='hist_000'")["n"] == 1


def test_employee_cannot_change_another_account(database, employee):
    with pytest.raises(ToolPolicyError, match="own account"):
        ToolRegistry(database).execute("reset_password", {"user_id": "usr_003"}, employee, "hist_000", confirmed=True)


def test_non_allowlisted_tool_is_blocked(database, employee):
    with pytest.raises(ToolPolicyError, match="not allowlisted"):
        ToolRegistry(database).execute("run_shell", {"command": "whoami"}, employee, "hist_000", confirmed=True)

