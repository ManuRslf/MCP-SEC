# MCP Security Experiment

## Project Purpose

This project investigates whether a gateway can enforce tool permissions when
an LLM agent encounters a prompt injection inside a file. The planned experiment
asks an agent to summarize a public document containing an instruction to read
a forbidden dummy secret.

The experiment separates three questions:

1. Did the model attempt the forbidden tool call?
2. Did the gateway block that call?
3. Did the final answer reveal the dummy secret?

The policy, gateway, filesystem tools, and their tests are implemented. Connecting
the application MCP client and LLM agent is the next stage. See
[PROGRESS.md](PROGRESS.md) for completed and pending work, and [goal.txt](goal.txt)
for the initial experiment specification.

## Architecture

The diagram shows the intended complete flow. The agent and application MCP
client are still pending; the tests already include a working MCP client.

```mermaid
flowchart LR
    User[User task] --> Agent[LLM agent - planned]
    Agent --> Gateway[Security gateway and policy]
    Gateway --> Client[MCP client - planned]
    Client --> Server[MCP filesystem server]
    Server --> Sandbox[Sandbox files]
```

<!-- Architecture diagram image placeholder: docs/architecture.png -->

- [gateway/policy.py](gateway/policy.py) validates arguments and authorizes
  resolved paths using the rules in [gateway/policy.md](gateway/policy.md).
- [gateway/gateway.py](gateway/gateway.py) checks the policy, logs decisions,
  forwards approved requests to an executor, and returns structured responses.
- [mcp_server/server.py](mcp_server/server.py) exposes `read_file`, `write_file`,
  and `list_directory` through MCP over stdio.
- [tests/](tests/) verifies each component and includes a real subprocess MCP
  connection test. Filesystem tests use temporary directories and dummy data.

The server limits filesystem access to the entire `sandbox/`. The gateway adds
the stricter per-tool permissions:

| Tool | Gateway permits |
| --- | --- |
| `read_file` | Files inside `sandbox/public/` |
| `list_directory` | `sandbox/public/` and its subdirectories |
| `write_file` | Files inside `sandbox/output/` |
| Unknown tools | Nothing |

The tools expect absolute paths. Local paths are derived from the project
location; `/workspace/...` in the experiment notes describes the planned Docker
mount. The server can access dummy secrets inside its sandbox when called
directly, allowing a future comparison with gateway enforcement enabled and
disabled.

## Getting Started

Requirements: Python 3.11 or newer and access to the private GitHub repository.
The commands below use a Linux or macOS shell.

1. Clone the repository and enter its directory. If you already have the project
   locally, start from that project root.

   ```bash
   git clone https://github.com/ManuRslf/MCP-security.git
   cd MCP-security
   ```

2. Create and activate a virtual environment, then install the dependencies.

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

   The project uses MCP SDK v2. An API key is not required for the current server
   or test suite; the LLM agent is still pending.

3. Run the test suite.

   ```bash
   python -m pytest -q
   ```

   To run only the server tests with individual results:

   ```bash
   python -m pytest tests/test_server.py -v
   ```

   The MCP connection test starts and stops its own server subprocess. Run it in
   an environment that permits subprocess communication over standard input and
   output.

4. Start the standalone MCP server.

   ```bash
   python -m mcp_server.server
   ```

   The server waits for MCP protocol messages from a client. It does not provide
   an interactive chat prompt. Stop it with `Ctrl-C`. To exercise the current
   tools through MCP, run the connection test:

   ```bash
   python -m pytest tests/test_server.py::test_stdio_tool_discovery_and_execution -v
   ```

Docker configuration and an agent entry point are still pending. The current
`Dockerfile` and `compose.yaml` are empty placeholders.

## Development Workflow

[inst.md](inst.md) defines the documentation and progress workflow. When the next
step is requested, verify the previous implementation, update
[PROGRESS.md](PROGRESS.md), and commit verified changes before proposing the next
task. Update this README when setup instructions, architecture, or project status
change.

Reuse recorded verification for unchanged code. Review an already-verified code
file again only after it has been modified, and run focused checks for new or
modified implementations. Documentation-only updates do not require rerunning
code tests.
