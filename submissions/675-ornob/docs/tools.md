# Tools

How tools are defined, registered, executed, and how to add a new one.

---

## What Is a Tool?

In LangGraph, a tool is a function the LLM can call by name. The model sees a JSON schema describing the tool's name, description, and parameters. When it decides to use a tool, it emits an `AIMessage` with a `tool_calls` list. The graph routes that message to the corresponding tool node, executes it, and feeds the result back as a `ToolMessage`.

This project wraps that concept in three layers:

```
ToolRegistration     ← metadata (name, schema, handler, node name, has_retry)
    │
ToolHandler          ← async class with a handle() method
    │
tool_node()          ← generic LangGraph node that resolves handler from registry
```

---

## The Registry

`ToolRegistry` (in `library/registry/tool_registry.py`) is the single source of truth. The graph reads it at build time to:

- Generate the tool schema list bound to Ollama
- Create a node for each tool
- Wire routing edges (conditional for `has_retry=True`, direct for `has_retry=False`)

```python
@dataclass(frozen=True)
class ToolRegistration:
    name: str                  # tool name the LLM uses
    handler_class: type        # class with a handle() method
    schema: BaseTool           # LangChain tool schema (for LLM binding)
    node_name: str             # LangGraph node name
    has_retry: bool = False    # True → wires conditional edge to sql_repair_node
```

`builtin_tools.py` registers all three built-in tools at import time:

```python
tool_registry.register(ToolRegistration(
    name="run_sql",
    handler_class=RunSqlHandler,
    schema=RunSqlTool(),
    node_name="run_sql_node",
    has_retry=True,       # SQL failures trigger the repair loop
))
```

---

## Built-in Tools

### `think`

**Assignment requirement:** give non-reasoning models an explicit chain-of-thought slot before acting.

```
Input:  thought (str) — the model's reasoning
Output: ThinkingEvent(type="thinking", content=thought)
```

Implementation (`tools/think.py`): one line — create and return a `ThinkingEvent`. No side effects, no I/O. The model calls this before making decisions; the graph stores the result as a `ToolMessage` in state.

`has_retry=False` — a think call can never fail in a meaningful way.

---

### `run_sql`

**Assignment requirement:** execute a read-only SQL statement and return rows the LLM can read.

```
Input:  query (str) — a SQL SELECT statement
Output: DbResultEvent (success) or ErrorEvent (failure)
```

Execution pipeline (`db/sql_guard.py` → `db/query_executor.py`):

```
query string
    │
    ▼
validate_sql()         ← synchronous, fast
    │
    ├── non-empty?
    ├── starts with SELECT?
    ├── no semicolon?          (trailing ; stripped automatically)
    └── no destructive keyword?
    │
    ▼ (passes all rules)
QueryExecutor.execute()
    │
    ├── SET LOCAL statement_timeout = N ms
    ├── SELECT ... LIMIT {db_max_rows}   ← row cap appended if missing
    └── fetchmany(db_max_rows)
    │
    ▼
DbResultEvent(sql, rows, row_count)
```

On any failure: returns `ErrorEvent`. `tool_node` sees `event.type == "error"` and increments `sql_retry_count`. `route_after_db_query` then decides whether to retry.

`has_retry=True` — wires a conditional edge so failures trigger `sql_repair_node`.

---

### `db_schema`

Not required by the assignment but added so the agent can inspect the database schema before writing SQL.

```
Input:  table_name (str | None) — optional filter
Output: str — formatted table/column metadata from information_schema
```

`has_retry=False` — schema queries run against `information_schema` and do not need a repair loop.

---

## How `tool_node` Works

All three tools share the same generic `tool_node` function. The graph creates a partial for each:

```python
partial(tool_node, executor=executor, tool_name="run_sql")
```

At runtime, `tool_node`:
1. Reads `state["messages"][-1]` — must be an `AIMessage` with `tool_calls`.
2. Looks up the handler from the registry by `tool_name`.
3. Calls `handler.handle(executor, **tool_call["args"])`.
4. Wraps the result in a `ToolMessage`.
5. If `has_retry`: checks `event.type` to increment or reset `sql_retry_count`.

---

## Adding a New Tool

Four steps, no changes to the graph:

**1. Write the handler** (`library/tools/my_tool.py`):

```python
from library.api.events import AssistantTextEvent, ErrorEvent

class MyToolHandler:
    async def handle(self, executor, *, my_param: str):
        # do something
        return AssistantTextEvent(content=f"Result: {my_param}")
```

**2. Write the schema** (`library/tools/schemas.py`):

```python
class MyToolInput(BaseModel):
    my_param: str = Field(description="What this parameter does")

class MyTool(BaseTool):
    name: str = "my_tool"
    description: str = "One sentence the LLM reads to decide when to call this."
    args_schema: type[BaseModel] = MyToolInput

    def _run(self, **kwargs): ...  # not used; agent uses async handler
```

**3. Register it** (`library/registry/builtin_tools.py`):

```python
tool_registry.register(ToolRegistration(
    name="my_tool",
    handler_class=MyToolHandler,
    schema=MyTool(),
    node_name="my_tool_node",
    has_retry=False,
))
```

**4. Done.** The graph picks it up automatically on the next `create_graph()` call. The LLM sees the new tool in its schema. No changes to `graph_factory.py`, `router.py`, or `nodes.py`.

---

## Tool Call Tracing

`library/agent/tracing.py` provides utilities to inspect what tools were called in the current turn:

```python
from library.agent.tracing import current_turn_tool_call_names

call_sequence = current_turn_tool_call_names(state)
# e.g. ['think', 'run_sql']
```

Internals:
- `current_turn_messages(state)` — slices `state["messages"]` from after the last user `HumanMessage` (skipping `name="repair"` messages injected by `sql_repair_node`)
- `tool_call_names(messages)` — extracts `tc["name"]` from every `AIMessage.tool_calls`

Used in notebook Case 6 to verify `think` fires before `run_sql`.
