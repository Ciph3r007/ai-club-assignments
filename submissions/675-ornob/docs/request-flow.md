# Request Flow

How a single user message travels through the system from caller to response.

---

## Entry Point

```python
events = await service.run_turn(session, "Top 5 customers by order value?")
```

`GraphAgentService.run_turn` does three things before touching the graph:

1. **Ownership check** — `InMemoryOwnershipStore` verifies `session.user_id` owns `session.thread_id`. If not, returns
   `ErrorEvent(OwnershipError)` immediately.
2. **Invokes the graph** — calls `graph.ainvoke({"messages": [HumanMessage(...)], "sql_retry_count": 0}, config)` with
   the `thread_id` as the checkpoint key.
3. **Extracts events** — walks the returned state and converts `ToolMessage` and `AIMessage` objects into typed
   `AgentEvent` objects.

---

## Graph Execution

The graph is a `StateGraph` compiled from these nodes and edges:

```
                    ┌───────────────┐
                    │  call_model   │ ◀──────────────────┐
                    │   (Ollama)    │                     │
                    └──────┬────────┘                     │
                           │                              │
                    route_after_model                     │
                    (reads last AIMessage's tool_calls)   │
                           │                              │
          ┌────────────────┼────────────────┐             │
          ▼                ▼                ▼             │
    ┌──────────┐    ┌──────────┐    ┌────────────┐        │
    │think_node│    │run_sql_  │    │db_schema_  │        │
    │          │    │node      │    │node        │        │
    └────┬─────┘    └────┬─────┘    └─────┬──────┘        │
         │              │                 │               │
      (no retry)   route_after_db_query  (no retry)      │
         │              │                 │               │
         │         ┌────┴────┐            │               │
         │         ▼         ▼            │               │
         │   ┌──────────┐  call_model ────┘               │
         │   │sql_repair│                                 │
         │   │_node     │─────────────────────────────────┘
         │   └──────────┘
         │
         └──────────────────────────────────────────────▶ call_model ──▶ __end__
```

### Step by step for a SQL question

| Step | What happens                                                                                                                                                                                                                           |
|------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1    | `call_model` invokes Ollama with `SystemMessage + full message history`. Model decides to call `db_schema`.                                                                                                                            |
| 2    | `route_after_model` reads `AIMessage.tool_calls[0].name` → routes to `db_schema_node`.                                                                                                                                                 |
| 3    | `db_schema_node` queries `information_schema`, returns a `ToolMessage` with column metadata.                                                                                                                                           |
| 4    | `route_after_model` routes to `call_model` (no tool call pending).                                                                                                                                                                     |
| 5    | `call_model` invokes Ollama again. Now the model has schema context. It calls `run_sql` with a `SELECT` query.                                                                                                                         |
| 6    | `route_after_model` → `run_sql_node`.                                                                                                                                                                                                  |
| 7    | `run_sql_node` runs `sql_guard.validate_sql` (sync). If it passes, `QueryExecutor.execute` runs the query. Returns `DbResultEvent` (success) or `ErrorEvent` (failure). `sql_retry_count` increments on error, resets to 0 on success. |
| 8    | `route_after_db_query`: if `0 < retry_count ≤ 3` → `sql_repair_node`; else → `call_model`.                                                                                                                                             |
| 9    | `call_model` reads the result rows and writes the final answer. No more tool calls → `__end__`.                                                                                                                                        |

---

## State

`AgentState` carries two fields:

```python
class AgentState(MessagesState):
    sql_retry_count: int
```

`MessagesState` gives `messages: Annotated[list[BaseMessage], add_messages]`.

**`add_messages` reducer:** every node returns `{"messages": [new_message]}`. LangGraph *appends* rather than replaces.
After a full conversation the list looks like:

```
HumanMessage("My name is Alice")        ← Turn 1 input
AIMessage("Hello Alice!")               ← Turn 1 output
HumanMessage("Top 5 customers?")        ← Turn 2 input
AIMessage(tool_calls=[db_schema])
ToolMessage(schema_text)
AIMessage(tool_calls=[run_sql])
ToolMessage(db_result_json)
AIMessage("Top 5 are: ...")             ← Turn 2 output
```

This full list is replayed to the model on every `call_model` invocation — that is how memory works.

---

## The SQL Retry Cycle

When `run_sql` fails, the graph does not give up immediately:

```
run_sql_node (error) → sql_retry_count = 1
    ↓
route_after_db_query: 0 < 1 ≤ 3 → sql_repair_node
    ↓
sql_repair_node injects:
  HumanMessage("[SQL repair - attempt 1/3] The previous SQL query failed.
               Review the error above and retry with a corrected query.",
               name="repair")
    ↓
call_model sees the error + repair prompt → retries run_sql
    ↓
run_sql_node (success) → sql_retry_count = 0
    ↓
route_after_db_query: 0 < 0 is False → call_model → final answer
```

Maximum 3 retries (`MAX_SQL_RETRIES = 3` in `router.py`). After the 4th failure, `retry_count = 4 > 3`, so
`route_after_db_query` routes to `call_model` which tells the user the query could not be completed.

Repair `HumanMessage` objects are tagged `name="repair"` so that `current_turn_messages` in `tracing.py` skips them when
finding the turn boundary — otherwise tool calls before the first retry (like `think`) would be invisible to the tracer.

---

## Multi-Turn Memory

**How it works:**

`MemorySaver` stores the full `AgentState` (including all `messages`) in a Python dict keyed by `thread_id`. When
`run_turn` is called again on the same `thread_id`:

1. LangGraph loads the checkpoint for that `thread_id`.
2. The new `HumanMessage` is appended via `add_messages`.
3. The graph runs with the full accumulated history.
4. The updated state is saved back to `MemorySaver`.

The model "remembers" because it literally receives every prior message in its context window.

**Thread isolation:** different `thread_id` values are separate checkpoint keys. Starting a new thread gives the model
no memory of any previous thread.

**Assignment requirement met (Case 1 in notebook):**

```
Turn 1: "My name is Alice."  → model responds
Turn 2: "What is my name?"   → model answers "Alice" from checkpoint history
```

---

## Event Extraction

After `ainvoke` returns, `_extract_events_from_state` converts the raw state into `AgentEvent` objects:

1. Calls `current_turn_messages(state)` to get only messages from the current turn (after the last user `HumanMessage`).
2. For each `ToolMessage` in that slice: tries `json.loads(content)`. If `type == "db_result"` → appends
   `DbResultEvent`.
3. Reads the last `AIMessage` for the final text → appends `AssistantTextEvent`.
4. Always appends `DoneEvent` last.

---

## Streaming

`stream_turn` uses `astream_events(version="v2")` instead of `ainvoke`. It yields `AssistantTextEvent` objects one token
at a time by filtering `on_chat_model_stream` events. Tool-call construction chunks are silently dropped — only visible
prose reaches the caller.

---

## Ollama Fallback

`OllamaClient` tries the primary model first. If the model returns a response with no tool calls but the text looks like
a JSON tool call, the fallback parser (`_try_parse_tool_call_from_text` in `nodes.py`) extracts it. If the primary model
fails entirely, the client retries with each model in `ollama_fallback_models` from `.env`.
