from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SANDBOX_ROOT = PROJECT_ROOT / "sandbox"

ALLOWED_ROOTS = {
    "read_file": (SANDBOX_ROOT / "public").resolve(),
    "list_directory": (SANDBOX_ROOT / "public").resolve(),
    "write_file": (SANDBOX_ROOT / "output").resolve(),
}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    resolved_path: Path | None = None


def authorize(tool_name: str, arguments: dict) -> PolicyDecision:
    if not isinstance(tool_name, str) or tool_name not in ALLOWED_ROOTS:
        return PolicyDecision(
            False,
            f"Tool [{tool_name}] not recognized."
        )

    if not isinstance(arguments, dict):
        return PolicyDecision(
            False,
            "Arguments must be a dictionary."
        )

    required_keys = {"path", "content"} if tool_name == "write_file" else {"path"}
    if set(arguments) != required_keys:
        return PolicyDecision(
            False,
            f"Arguments must contain exactly these keys: {sorted(required_keys)}."
        )

    path_value = arguments["path"]
    if not isinstance(path_value, str) or not path_value.strip():
        return PolicyDecision(
            False,
            "The 'path' argument must be a nonempty string."
        )

    if tool_name == "write_file" and not isinstance(arguments["content"], str):
        return PolicyDecision(
            False,
            "The 'content' argument must be a string."
        )

    path = Path(path_value)

    if not path.is_absolute():
        return PolicyDecision(
            False,
            f"Path [{path_value}] is not absolute."
        )

    resolved_path = None
    try:
        try:
            resolved_path = path.resolve(strict=True)
        except FileNotFoundError:
            if tool_name != "write_file":
                return PolicyDecision(False, f"Path [{path}] does not exist.")
            # Writes may create files, but still resolve dangling symlink targets.
            resolved_path = path.resolve(strict=False)

        allowed_root = ALLOWED_ROOTS[tool_name].resolve(strict=True)
        try:
            resolved_path.relative_to(allowed_root)
        except ValueError:
            return PolicyDecision(
                False,
                f"Path [{resolved_path}] is outside allowed root [{allowed_root}].",
                resolved_path
            )

        if tool_name == "read_file":
            if not resolved_path.is_file():
                return PolicyDecision(
                    False,
                    f"Path [{resolved_path}] is not a file.",
                    resolved_path
                )
            return PolicyDecision(
                True,
                "Read operation authorized.",
                resolved_path
            )

        if tool_name == "write_file":
            if not resolved_path.parent.is_dir():
                return PolicyDecision(
                    False,
                    f"Parent [{resolved_path.parent}] is not an existing directory.",
                    resolved_path
                )
            if resolved_path.exists() and not resolved_path.is_file():
                return PolicyDecision(
                    False,
                    f"Path [{resolved_path}] is not a regular file.",
                    resolved_path
                )
            return PolicyDecision(
                True,
                "Write operation authorized.",
                resolved_path
            )

        if tool_name == "list_directory":
            if not resolved_path.is_dir():
                return PolicyDecision(
                    False,
                    f"Path [{resolved_path}] is not a directory.",
                    resolved_path
                )
            return PolicyDecision(
                True,
                "Directory listing authorized.",
                resolved_path
            )

    except (OSError, ValueError, RuntimeError):
        return PolicyDecision(False, "Path could not be validated.", resolved_path)

    return PolicyDecision(
        False,
        f"No authorization policy implemented for [{tool_name}].",
        resolved_path
    )
