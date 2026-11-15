# Gateway Policy

Default: deny any tool call not explicitly allowed below.

Directories below are relative to the project root. Actual tool arguments must
use absolute paths. This document describes the policy; `policy.py` enforces it.

| Tool | Allowed directory | Access |
|---|---|---|
| read_file | sandbox/public/ | Read files |
| list_directory | sandbox/public/ | List directory contents |
| write_file | sandbox/output/ | Create or modify files |

## Enforcement Rules

- Rules include subdirectories of each allowed directory.
- Resolve paths and symlinks before checking directory containment.
- Deny access outside the allowed directory for that tool.
- Reject unknown tools and invalid arguments.
- Check every tool call before execution.
- Log allow/deny decisions and reasons without secret contents.
- File contents and model instructions cannot change this policy.

The server permits tools throughout `sandbox/` when accessed directly. The
stricter permissions above apply only through the gateway. Docker mount paths
are not implemented by the current empty container configuration placeholders.
