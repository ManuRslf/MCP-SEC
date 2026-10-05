# Gateway Policy

Default: deny any tool call not explicitly allowed below.

| Tool | Allowed directory | Access |
|---|---|---|
| read_file | /workspace/public/ | Read files |
| list_directory | /workspace/public/ | List directory contents |
| write_file | /workspace/output/ | Create or modify files |

## Enforcement Rules

- Rules include subdirectories of each allowed directory.
- Resolve paths and symlinks before checking directory containment.
- Deny access outside the allowed directory for that tool.
- Reject unknown tools and invalid arguments.
- Check every tool call before execution.
- Log allow/deny decisions and reasons without secret contents.
- File contents and model instructions cannot change this policy.