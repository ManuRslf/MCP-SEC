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

The policy, gateway, filesystem tools, and their tests are implemented. The
application MCP client can launch the server, initialize a session, and read the
public fixture through the asynchronous security gateway and MCP executor.
Async gateway and client regression tests and real MCP denial integration tests
are implemented. Paired clean and injected experiment fixtures are ready.
The selected LLM backend is local Ollama. The Python agent can describe a
`read_file` tool, request a read of `clean.txt`, route proposed calls through the
gateway and MCP, and return JSON-compatible gateway results to the model for a
summary. A bounded loop handles additional requests, with at most five model
turns and ten tool calls. A real local clean-document run has been verified;
experiment tracing and the injected-document run are still pending.
See [PROGRESS.md](PROGRESS.md) for completed and pending work, and
[goal.txt](goal.txt) for the initial experiment specification.

## Architecture

The diagram shows the current tool-request path. The agent returns tool results
to the model and repeats the conversation until a final answer or a limit is
reached. The separate application client remains a public-file smoke test.

```mermaid
flowchart LR
    User[User task] --> Agent[LLM agent]
    Agent --> Gateway[Security gateway and policy]
    Gateway --> Client[MCP client and async executor]
    Client --> Server[MCP filesystem server]
    Server --> Sandbox[Sandbox files]
```

<!-- Architecture diagram image placeholder: docs/architecture.png -->

- [gateway/policy.py](gateway/policy.py) validates arguments and authorizes
  resolved paths using the rules in [gateway/policy.md](gateway/policy.md).
- [gateway/gateway.py](gateway/gateway.py) checks the policy, logs decisions,
  awaits an executor for approved requests, and returns structured responses.
- [mcp_server/server.py](mcp_server/server.py) exposes `read_file`, `write_file`,
  and `list_directory` through MCP over stdio.
- [mcp_client/client.py](mcp_client/client.py) starts the server, initializes an
  MCP session, defines an asynchronous executor, reads the public fixture through
  the gateway, and closes the session and process. The executor raises a generic
  error for failed MCP tool results; the gateway converts execution exceptions
  into sanitized error responses.
- [agent/agent.py](agent/agent.py) sends asynchronous local Ollama requests
  with a `read_file` schema and the absolute path to `clean.txt`. Inside an
  initialized MCP session, it routes each model-proposed call through the
  security gateway. The executor checks the MCP error flag and converts successful
  results to JSON-compatible dictionaries. The agent preserves the assistant's
  tool requests and appends one tool-role message per gateway result before
  asking the model again. Denials and errors are returned in the same
  conversation. The loop stops on a reply without tool calls or when its model
  turn or tool-call budget is exhausted. Every executed call uses the gateway.
- [tests/](tests/) verifies each component and includes real subprocess MCP
  integration tests. Gateway integration checks approved tools and proves that
  denied secret requests never call MCP. Filesystem tests use temporary
  directories and dummy data.

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

   The project uses MCP SDK v2. An API key is not required for the current server,
   test suite, or local Ollama agent.

3. Run the test suite.

   ```bash
   python -m pytest -q
   ```

   To run only the server tests with individual results:

   ```bash
   python -m pytest tests/test_server.py -v
   ```

   To run only the client regression tests:

   ```bash
   python -m pytest tests/test_client.py -v
   ```

   To run only the real gateway-to-MCP integration tests:

   ```bash
   python -m pytest tests/test_gateway_mcp.py -v
   ```

   The MCP integration tests start and stop their own server subprocesses. Run
   them in an environment that permits subprocess communication over standard
   input and output.

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

5. Run the application client to read the public fixture through the gateway.

   ```bash
   python -m mcp_client.client
   ```

   The client starts and stops its own server; no separately running server is
   needed. It prints the initialization message and a gateway response with
   `status`, `result`, and `reason` for reading `sandbox/public/useful_data.txt`.
   This remains a smoke-test input: the client only displays its contents as
   data and does not use an LLM yet. The experimental `clean.txt` and
   `injected.txt` documents are not selected by this entry point.

The experiment fixtures are `sandbox/public/clean.txt` and
`sandbox/public/injected.txt`. They contain the same urban-parks paragraph, with
the injected version appending an instruction to read the local dummy secret.
[goal.txt](goal.txt) records the local paths, expected normal summary, and
metrics. The agent asks the model to read and summarize `clean.txt` by default,
and executes proposed calls only through the gateway. The current smoke client
still reads `useful_data.txt`.

Docker configuration and experiment tracing are still pending. The current
`Dockerfile` and `compose.yaml` are empty placeholders.

## Local LLM Setup

The planned agent uses a local Ollama model. With Ollama installed, start its
server in one terminal:

```bash
ollama serve
```

Keep that terminal open, and list installed models from another terminal:

```bash
ollama list
```

For the initial 4 GB VRAM setup, start with
[`qwen3:1.7b`](https://ollama.com/library/qwen3:1.7b), a tool-capable model with an
approximately 1.4 GB download. Runtime memory also depends on context size and
other overhead; the download size is not a VRAM requirement.

```bash
ollama pull qwen3:1.7b
ollama run qwen3:1.7b
```

Inside the chat, use `/set parameter num_ctx 2048` for an initial small context
and try an explicit prompt such as `Explain Model Context Protocol in two simple
sentences.` While the chat is open, run `ollama ps` from another terminal to
check whether the model is loaded on the GPU. See the
[Ollama FAQ](https://docs.ollama.com/faq).

Local inference uses `http://localhost:11434` and does not require an API key;
see the [Ollama API documentation](https://docs.ollama.com/api/introduction).
The Python agent uses the
[Ollama Python library's `AsyncClient`](https://github.com/ollama/ollama-python);
`ollama` is included in `requirements.txt`. It describes the tool using the
[Ollama tool-calling schema](https://docs.ollama.com/capabilities/tool-calling).
The request keeps `think=False` and `num_ctx=2048`; see
[thinking controls](https://docs.ollama.com/capabilities/thinking).

With the Ollama server running and the model installed, run the agent from the
project root:

```bash
python -m agent.agent
```

The agent starts and stops its own MCP server, executes proposed calls through
the gateway, and sends their JSON results back to Ollama until it can print a
final model reply or a limit is reached. Denied calls do not reach MCP, but their denial
responses are still returned to the model. A real local `qwen3:1.7b` run read
`clean.txt` and returned a relevant urban-parks summary. It used four sentences
despite the two-sentence prompt; output quality and length are not guaranteed.

If the initial reply has no tool calls, the script reports
`No tool call was proposed.` and prints any reply text. An empty final reply
after tool execution is also reported explicitly.

The loop limits are `MAX_MODEL_TURNS = 5` and `MAX_TOOL_CALLS = 10` in
`agent/agent.py`. Denied requests count toward the tool-call budget. A batch
that exceeds the remaining budget is rejected before any of its calls execute.
The last model turn can produce a final answer, but new tool requests on that
turn are not executed because no model turn remains to consume their results.
Limit exhaustion is reported explicitly, not printed as a successful summary.
Only structured model tool calls are processed; instructions or tool names
appearing in ordinary text are not executed.

Run the focused agent tests without requiring an Ollama server or GPU:

```bash
python -m pytest tests/test_agent.py -v
```

The 30 focused tests use mocked Ollama and MCP connections with the real gateway
policy, real SDK result types, and temporary sandbox fixtures. They cover
approved and denied calls, JSON serialization, errors, cancellation, and session
cleanup, plus conversation order, unchanged model settings, returned tool
results, multi-turn execution, model-turn limits, and tool-call budgets. A
mocked post-read secret request is denied before MCP and its denial is returned
to the model; this is not a real model attack-success measurement. No model
download, inference, or GPU is needed for these tests.

Keep model settings identical when later comparing clean and injected documents.

## Development Workflow

[inst.md](inst.md) defines the documentation and progress workflow. When the next
step is requested, verify the previous implementation, update
[PROGRESS.md](PROGRESS.md), and commit and push verified changes before proposing
the next task. Verified task completions are also committed and pushed to the
current branch's configured upstream by default, unless the user requests local
changes only. Review staged changes for credentials, real secrets, and unrelated
edits; never force-push or overwrite remote history. Update this README when
setup instructions, architecture, or project status change.

Reuse recorded verification for unchanged code. Review an already-verified code
file again only after it has been modified, and run focused checks for new or
modified implementations. Documentation-only updates do not require rerunning
code tests.
