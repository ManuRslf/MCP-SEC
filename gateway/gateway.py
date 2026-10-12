import logging
from collections.abc import Callable
from .policy import authorize


class SecurityGateway:
    def __init__(self,
                 executor: Callable[[str, dict], object],
                 logger: logging.Logger | None = None,
                 ) -> None:
        self.executor = executor
        self.logger = logger if logger is not None else logging.getLogger(__name__)

    def execute(
        self,
        tool_name: str,
        arguments: dict,
    ) -> dict:
        decision = authorize(tool_name, arguments)

        self.logger.info(
            "tool=%s allowed=%s reason=%s",
            tool_name,
            decision.allowed,
            decision.reason,
        )

        if not decision.allowed:
            return {
                "status": "denied",
                "result": None,
                "reason": decision.reason,

            }

        approved_arguments = arguments.copy()
        approved_arguments["path"] = str(decision.resolved_path)

        try:
            result = self.executor(tool_name, approved_arguments)
        except Exception:
            return {
                "status": "error",
                "result": None,
                "reason": "Tool execution failed.",
            }

        return {
            "status": "success",
            "result": result,
            "reason": None,
        }
