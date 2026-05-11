# Architecture

## What It Is

A multi-turn conversational agent that answers questions about a PostgreSQL database (Northwind). The user asks
questions in plain English; the agent writes and executes SQL, reasons step by step, and remembers prior turns in the
same conversation.

Built on **LangGraph** (graph-based agent orchestration), **Ollama** (local LLM), and **PostgreSQL** (via SQLAlchemy).

---

## Assignment Requirements — Where Each Is Met

| Requirement                       | Where                                                                    |
|-----------------------------------|--------------------------------------------------------------------------|
| LangGraph ReAct agent             | `library/agent/graph_factory.py` — `create_graph()`                      |
| `run_sql` tool                    | `library/tools/db_query.py` — `RunSqlHandler`                            |
| `think` tool                      | `library/tools/think.py` — `ThinkHandler`                                |
| `MemorySaver()` checkpointer      | `graph_factory.py` line: `MemorySaver()` passed to `builder.compile()`   |
| Multi-turn memory within a thread | `AgentState.messages` + `add_messages` reducer + `MemorySaver`           |
| `think → run_sql` trace           | Notebook Case 6; verified by `current_turn_tool_call_names`              |
| Database seeded with data         | Northwind PostgreSQL, loaded via `Dockerfile.postgres` + `northwind.sql` |
| Notebook readable end-to-end      | `week-01/week-01.ipynb` — Cases 1–7 with annotated markdown              |

---

## Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Notebook / Caller                    │
└────────────────────────────┬────────────────────────────┘
                             │ run_turn(session, message)
                             ▼
┌─────────────────────────────────────────────────────────┐
│                  GraphAgentService                      │
│  - Ownership check (InMemoryOwnershipStore)             │
│  - Calls graph.ainvoke()                                │
│  - Converts state → AgentEvent list                     │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│              LangGraph StateGraph (compiled)            │
│                                                         │
│   ┌─────────────┐    ┌──────────────┐    ┌──────────┐   │
│   │ call_model  │───▶│  tool nodes  │───▶│sql_repair│   │
│   │  (Ollama)   │◀───│  (think /    │    │  _node   │   │
│   └─────────────┘    │  run_sql /   │    └──────────┘   │
│                      │  db_schema)  │                   │
│                      └──────────────┘                   │
│                                                         │
│   State: { messages: [...], sql_retry_count: int }      │
│   Checkpointer: MemorySaver (keyed by thread_id)        │
└────────────────────────────┬────────────────────────────┘
                             │
                  ┌──────────┼──────────┐
                  ▼          ▼          ▼
            ┌─────────┐ ┌────────┐ ┌──────────┐
            │ Ollama  │ │sql_    │ │QueryExec │
            │  LLM    │ │guard   │ │  utor    │
            └─────────┘ └────────┘ └──────────┘
                                        │
                                        ▼
                                  ┌────────────┐
                                  │ PostgreSQL │
                                  │ (Northwind)│
                                  └────────────┘
```

---

## Layer Breakdown

### `api/`

The public contract. Nothing outside `library/` depends on internals.

- **`events.py`** — typed event objects the agent returns. Every response is one or more of:
    - `ThinkingEvent` — the model's chain-of-thought (from `think` tool)
    - `DbResultEvent` — SQL result rows
    - `AssistantTextEvent` — final natural language answer
    - `ErrorEvent` — guard rejection, DB failure, or ownership violation
    - `DoneEvent` — always last, signals end of response
- **`service.py`** — abstract `AgentService` base class + `SessionContext(thread_id, user_id)`

### `agent/`

The graph and its internals.

- **`state.py`** — `AgentState` extends LangGraph's `MessagesState`. Adds `sql_retry_count` to track consecutive SQL
  failures.
- **`graph_factory.py`** — builds and compiles the `StateGraph`; contains `GraphAgentService` (the concrete service).
- **`nodes.py`** — three node functions: `call_model_node`, `tool_node` (generic), `sql_repair_node`.
- **`router.py`** — two routing functions: `route_after_model` (which tool to call) and `route_after_db_query` (retry or
  continue).
- **`tracing.py`** — utilities for inspecting which tools were called in the current turn.

### `tools/`

One file per tool. Each tool has a handler, a schema, and is registered in `registry/`.

- **`think.py`** — echoes the thought back. No side effects.
- **`db_query.py`** — validates SQL, executes it, returns rows or error.
- **`db_schema.py`** — queries `information_schema` and returns table/column metadata.

### `db/`

Everything that touches the database.

- **`sql_guard.py`** — pipeline of `SqlValidationRule` objects. Rejects non-SELECT statements, semicolons (
  multi-statement injection), and destructive keywords. Runs synchronously before any connection is opened.
- **`query_executor.py`** — opens a connection, sets `statement_timeout`, applies a row cap, returns `QueryResult`.

### `registry/`

Central tool registration. The graph reads tool schemas and routing info entirely from the registry — adding a tool
requires no changes to the graph.

- **`tool_registry.py`** — `ToolRegistry` holds `ToolRegistration` objects (name, handler, schema, node name,
  `has_retry` flag).
- **`builtin_tools.py`** — registers `think`, `run_sql`, `db_schema` at import time.

### `model/`

- **`ollama_client.py`** — wraps `ChatOllama`. On tool-call failure, falls back to the next model in
  `ollama_fallback_models`. Binds tool schemas from the registry.

### `session/`

- **`ownership.py`** — `InMemoryOwnershipStore` records `thread_id → user_id`. First caller claims the thread;
  subsequent callers with a different `user_id` get `OwnershipError` immediately.

### `config/`

- **`settings.py`** — Pydantic-Settings reads `.env`. Exposes DB URL, Ollama model, row cap, timeout, log level, and
  system prompt as typed fields.

---

## Key Design Decisions

**Why a `ToolRegistry`?**
The graph wires nodes and edges by reading the registry at build time. Adding a new tool means one
`tool_registry.register(...)` call — the graph, router, and LLM tool-binding all update automatically.

**Why typed events instead of strings?**
Callers (notebook, web API, tests) can pattern-match on `event.type` without parsing strings. The `DbResultEvent`
carries structured rows; the notebook's formatter and a future REST endpoint can both consume the same object.

**Why `sql_guard` runs before the DB connection?**
A rejected query never opens a connection, never counts against the pool, and never touches the database. Fast-fail at
the validation layer.

**Why `MemorySaver` and not `SqliteSaver`?**
Assignment constraint: in-process memory only. `MemorySaver` stores the full `messages` list for each `thread_id` in a
Python dict. It resets when the kernel restarts — no persistence, no leakage across sessions.
