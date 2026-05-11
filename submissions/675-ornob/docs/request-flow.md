# Request Flow

## What Happens When You Ask a Question?

Think of the agent like a smart research assistant:

1. You ask a question in plain English
2. The assistant checks the database structure so it knows what tables exist
3. It writes a SQL query
4. It runs the query
5. It reads the results and answers you in plain English

The difference from a regular assistant? Every step is logged, every tool call is tracked, and if the SQL fails, it
automatically tries to fix it.

---

## The Full Journey

```
  User          Service          LLM (Ollama)       PostgreSQL
   |                |                 |                  |
   |--"Top 5?"----> |                 |                  |
   |                |--ownership      |                  |
   |                |  check          |                  |
   |                |                 |                  |
   |                |--invoke-------> |                  |
   |                |  (full history) |                  |
   |                |                 |                  |
   |                |          "call db_schema"          |
   |                |                 |--schema query--> |
   |                |                 |<--column names-- |
   |                |                 |                  |
   |                |          "call run_sql"            |
   |                |                 |--SELECT query--> |
   |                |                 |<--rows---------- |
   |                |                 |                  |
   |                |          "Top 5 are: ..."          |
   |                |<--state---------|                  |
   |<--events------ |                 |                  |
   |  [DbResultEvent,                 |                  |
   |   AssistantTextEvent,            |                  |
   |   DoneEvent]                     |                  |
```

---

## Step-by-Step Walkthrough

### Step 1 — Ownership Check

Before anything runs, the service checks: *"Does this user own this conversation thread?"*

The first user to use a `thread_id` claims it. Anyone else gets an error immediately — the LLM never even sees the
message.

### Step 2 — LLM Thinks

The LLM receives the full conversation history (every message from every prior turn). It decides what to do next —
usually inspect the schema first, then write SQL.

### Step 3 — Tools Run

The graph executes whichever tool the LLM requested, feeds the result back, and the LLM thinks again. This loop repeats
until the LLM stops calling tools.

```
  ┌─────┐    wants tool    ┌──────────┐    result     ┌─────┐
  │ LLM │ ───────────────► │ Tool     │ ────────────► │ LLM │
  └─────┘                  │ executes │               └──┬──┘
                           └──────────┘                  │
                                                 no more tools
                                                         │
                                                         ▼
                                                  ┌─────────────┐
                                                  │ Final answer│
                                                  └─────────────┘
```

### Step 4 — Final Answer

When the LLM produces a response with no tool calls, the graph ends. The service converts the raw state into typed event
objects and returns them.

---

## Memory: How the Agent Remembers You

There is no special memory module. **The agent remembers because it reads the entire chat history every time.**

```
  Turn 1
  ──────
  User:  "My name is Alice."
  LLM receives: [ "My name is Alice." ]
  LLM replies:  "Hello Alice!"

  Turn 2
  ──────
  User:  "What is my name?"
  LLM receives: [ "My name is Alice."   ← still here
                  "Hello Alice!"
                  "What is my name?" ]
  LLM replies:  "Your name is Alice."
```

LangGraph stores this history in a `MemorySaver` — a Python dict keyed by `thread_id`. Each new turn appends to the
list; the full list goes to the LLM every time.

**Same thread — memory persists. Different thread — memory resets.**

```
  Thread A  (thread_id = "session-alice")
  ─────────────────────────────────────────────────
  Turn 1  →  "My name is Alice."
  Turn 2  →  "What is my name?"  →  LLM: "Alice."   (remembers)

  Thread B  (thread_id = "session-bob")
  ─────────────────────────────────────────────────
  Turn 1  →  "What is my name?"  →  LLM: "I don't know your name."
             (Thread B has zero history from Thread A)
```

`MemorySaver` is an in-process Python dict — no database, no file on disk. Restarting the Python kernel
wipes all threads. This satisfies the assignment constraint: conversations are not persisted.

---

## SQL Retry: Self-Healing Queries

If the LLM writes a broken SQL query, the agent does not give up. It tries to fix it automatically.

```
  run_sql(bad query)
       │
       ▼
  FAILED  ──► attempt 1 of 3
               │
               ▼
        "The query failed: <error>.
         Review and retry."
               │
               ▼
          LLM rewrites SQL
               │
               ▼
          run_sql(new query)
               │
         ┌─────┴─────┐
       success      failed ──► attempt 2 of 3 ──► (same cycle)
         │
         ▼
   continue to answer
```

Maximum 3 retries. After the 3rd failure the agent tells the user the query could not be completed.

---

## What the Service Returns

The agent does not return a string. It returns a list of typed events:

| Event                | What it contains                                                   |
|----------------------|--------------------------------------------------------------------|
| `ThinkingEvent`      | The LLM's chain-of-thought from the `think` tool                   |
| `DbResultEvent`      | The SQL that ran + the rows returned                               |
| `AssistantTextEvent` | The final plain-English answer                                     |
| `ErrorEvent`         | What went wrong (guard rejection, DB failure, ownership violation) |
| `DoneEvent`          | Always last — signals the response is complete                     |

---

## Streaming

Instead of waiting for the full answer, `stream_turn` yields tokens one by one as the LLM generates them — useful for
displaying a live typing effect in a UI.

```
  Caller                           Agent
    |                                |
    |---stream_turn(session, msg)--> |
    |                                |
    | <--AssistantTextEvent("Top")-- |
    | <--AssistantTextEvent(" 5")--- |
    | <--AssistantTextEvent(" are")- |
    | <--AssistantTextEvent("...")-- |
    | <--DoneEvent------------------ |
```
