import logging
from unittest.mock import Mock

import pytest

from gateway.gateway import SecurityGateway


@pytest.fixture
def executor():
    return Mock(return_value="Fake tool result")


@pytest.mark.parametrize("tool,folder,name", [
    ("read_file", "public", "document.txt"),
    ("list_directory", "public", ""),
    ("write_file", "output", "summary.txt"),
])
def test_allowed_requests_execute_once_and_return_success(sandbox, executor, tool, folder, name):
    path = sandbox[folder] / name
    arguments = {"path": str(path)}
    if tool == "write_file":
        arguments["content"] = "Summary"

    response = SecurityGateway(executor).execute(tool, arguments)

    executor.assert_called_once_with(tool, arguments)
    assert response == {
        "status": "success",
        "result": "Fake tool result",
        "reason": None,
    }


@pytest.mark.parametrize("tool", ["read_file", "list_directory", "write_file"])
@pytest.mark.parametrize("escape", ["direct", "traversal", "symlink"])
def test_secret_access_is_denied_without_execution(sandbox, executor, tool, escape):
    root = sandbox["output" if tool == "write_file" else "public"]
    name = "" if tool == "list_directory" else "password.txt"
    target = sandbox["secrets"] / name
    if escape == "direct":
        path = target
    elif escape == "traversal":
        path = root / ".." / "secrets" / name
    else:
        path = root / "escape"
        path.symlink_to(target, target_is_directory=tool == "list_directory")
    arguments = {"path": str(path)}
    if tool == "write_file":
        arguments["content"] = "Summary"

    response = SecurityGateway(executor).execute(tool, arguments)

    assert response["status"] == "denied"
    assert response["result"] is None
    assert response["reason"]
    executor.assert_not_called()


@pytest.mark.parametrize("tool", ["delete_file", None, []])
def test_unknown_tools_never_reach_executor(sandbox, executor, tool):
    arguments = {"path": str(sandbox["public"] / "document.txt")}

    response = SecurityGateway(executor).execute(tool, arguments)

    assert response["status"] == "denied"
    executor.assert_not_called()


@pytest.mark.parametrize("arguments", [
    None,
    ["path"],
    {},
    {"path": 123},
    {"path": "relative.txt"},
])
def test_invalid_arguments_never_reach_executor(executor, arguments):
    response = SecurityGateway(executor).execute("read_file", arguments)

    assert response["status"] == "denied"
    assert response["result"] is None
    assert response["reason"]
    executor.assert_not_called()


@pytest.mark.parametrize("invalid", ["missing_content", "wrong_content_type", "extra_key"])
def test_invalid_write_arguments_never_reach_executor(sandbox, executor, invalid):
    arguments = {"path": str(sandbox["output"] / "summary.txt"), "content": "Summary"}
    if invalid == "missing_content":
        arguments.pop("content")
    elif invalid == "wrong_content_type":
        arguments["content"] = 123
    else:
        arguments["unexpected"] = True

    response = SecurityGateway(executor).execute("write_file", arguments)

    assert response["status"] == "denied"
    executor.assert_not_called()


@pytest.mark.parametrize("tool", ["read_file", "list_directory", "write_file"])
def test_allowed_symlinks_forward_resolved_strings_without_mutating_input(sandbox, executor, tool):
    root = sandbox["output" if tool == "write_file" else "public"]
    target = root
    if tool == "read_file":
        target = root / "document.txt"
    elif tool == "write_file":
        target = root / "existing.txt"
        target.write_text("Existing document")
    link = root / "alias"
    link.symlink_to(target, target_is_directory=tool == "list_directory")
    arguments = {"path": str(link)}
    if tool == "write_file":
        arguments["content"] = "Summary"
    original_arguments = arguments.copy()
    expected_arguments = {**arguments, "path": str(target.resolve())}

    response = SecurityGateway(executor).execute(tool, arguments)

    assert response["status"] == "success"
    executor.assert_called_once_with(tool, expected_arguments)
    assert arguments == original_arguments
    assert isinstance(executor.call_args.args[1]["path"], str)


def test_executor_mutations_do_not_change_callers_arguments(sandbox, executor):
    arguments = {
        "path": str(sandbox["output"] / "summary.txt"),
        "content": "Original content",
    }
    original_arguments = arguments.copy()

    def mutate_arguments(tool, approved_arguments):
        approved_arguments.clear()
        return "Fake tool result"

    executor.side_effect = mutate_arguments

    response = SecurityGateway(executor).execute("write_file", arguments)

    assert response["status"] == "success"
    executor.assert_called_once()
    assert arguments == original_arguments


def test_callers_can_reuse_arguments(sandbox, executor):
    arguments = {"path": str(sandbox["public"] / "document.txt")}
    gateway = SecurityGateway(executor)

    first_response = gateway.execute("read_file", arguments)
    second_response = gateway.execute("read_file", arguments)

    assert first_response["status"] == second_response["status"] == "success"
    assert executor.call_count == 2


@pytest.mark.parametrize("error", [OSError, ValueError, RuntimeError])
def test_executor_exceptions_return_generic_errors(sandbox, executor, caplog, error):
    confidential_detail = "DUMMY_CONFIDENTIAL_EXCEPTION_DETAIL"
    executor.side_effect = error(confidential_detail)
    arguments = {"path": str(sandbox["public"] / "document.txt")}

    with caplog.at_level(logging.INFO, logger="gateway.gateway"):
        response = SecurityGateway(executor).execute("read_file", arguments)

    executor.assert_called_once()
    assert response == {
        "status": "error",
        "result": None,
        "reason": "Tool execution failed.",
    }
    assert confidential_detail not in str(response)
    assert confidential_detail not in caplog.text


@pytest.mark.parametrize("allowed", [True, False])
def test_default_logger_records_authorization_decision(sandbox, executor, caplog, allowed):
    path = sandbox["public"] / "document.txt" if allowed else sandbox["secrets"] / "password.txt"

    with caplog.at_level(logging.INFO, logger="gateway.gateway"):
        response = SecurityGateway(executor).execute("read_file", {"path": str(path)})

    assert response["status"] == ("success" if allowed else "denied")
    records = [record for record in caplog.records if record.name == "gateway.gateway"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "tool=read_file" in message
    assert f"allowed={allowed}" in message
    assert "reason=" in message
    if allowed:
        assert "Read operation authorized." in message
    else:
        assert response["reason"] in message


@pytest.mark.parametrize("status", ["success", "denied", "error"])
def test_custom_logger_excludes_content_results_and_exception_details(sandbox, executor, caplog, status):
    content = "DUMMY_WRITE_CONTENT_NOT_FOR_LOGS"
    result = "DUMMY_TOOL_RESULT_NOT_FOR_LOGS"
    exception_detail = "DUMMY_EXCEPTION_DETAIL_NOT_FOR_LOGS"
    executor.return_value = result
    if status == "error":
        executor.side_effect = OSError(exception_detail)
    root = sandbox["secrets" if status == "denied" else "output"]
    arguments = {"path": str(root / "summary.txt"), "content": content}
    logger = logging.getLogger("tests.security_gateway")

    with caplog.at_level(logging.INFO, logger=logger.name):
        response = SecurityGateway(executor, logger=logger).execute("write_file", arguments)

    assert response["status"] == status
    records = [record for record in caplog.records if record.name == logger.name]
    assert len(records) == 1
    assert "tool=write_file" in records[0].getMessage()
    assert content not in caplog.text
    assert result not in caplog.text
    assert exception_detail not in caplog.text
    if status == "denied":
        executor.assert_not_called()
    else:
        executor.assert_called_once()
