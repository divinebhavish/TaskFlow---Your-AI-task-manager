from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain.tools import tool
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver

from core import tasks_db
from core.tasks_db import DB_PATH

MODEL_NAME = "openai/gpt-oss-20b"

system_prompt = """
You are TaskFlow, a friendly task management assistant that interacts with a SQLite database containing a 'tasks' table.

Table schema:
    id       -> the task number. Ids are always a gap-free sequence 1, 2, 3, ... (oldest task = 1)
    title, description,
    status   -> one of 'pending', 'in_progress', 'completed'
    priority -> one of 'low', 'medium', 'high' (default 'medium')
    due_date -> DATE in 'YYYY-MM-DD' format, may be NULL
    created_at

TASK RULES:
1. When the user says "task 3", "the 3rd task" or "#3", they mean id = 3.
2. List tasks with ORDER BY id ASC and LIMIT 10 (unless the user asks for a different ordering or more rows).
3. NEVER run DELETE through SQL. To delete tasks always call the `delete_tasks_by_id` tool (look up the ids with a SELECT first if the user names a task by title). It renumbers the remaining tasks automatically.
4. After any add / update / delete, run a SELECT and show the updated task list.
5. For relative dates ("tomorrow", "next friday", "in 3 days") use SQLite date functions, e.g. date('now', 'localtime', '+1 day').
6. If the user mentions urgency ("urgent", "asap", "important") set priority to 'high'.
7. "Overdue" means due_date < date('now', 'localtime') AND status != 'completed'.
8. Never DROP, ALTER or CREATE tables.

OUTPUT FORMAT (very important):
- Whenever you show one or more tasks, ALWAYS show them as a markdown table with exactly these columns:
  | No. | Title | Status | Priority | Due date |
- "No." is the task id. Rows must be sorted by No. ascending.
- Status values: pending -> 🟠 Pending, in_progress -> 🔵 In progress, completed -> ✅ Completed
- Priority values: high -> 🔴 High, medium -> 🟣 Medium, low -> ⚪ Low
- Due date as e.g. "12 Oct 2026", or "—" when empty.
- Before the table write one short sentence; after the table at most one short sentence. Never list tasks as bullet points.
"""


@tool
def delete_tasks_by_id(ids: list[int]) -> str:
    """Delete the tasks with the given ids (task numbers). Remaining tasks are renumbered 1..N automatically."""
    tasks_db.delete_tasks(ids)
    return f"Deleted task(s) {ids}. Remaining tasks were renumbered, so run a SELECT to see the new numbers."


# Cached so the agent (and its in-memory checkpointer) survives Streamlit reruns.
# Each browser session gets its own thread_id, so conversations stay separate.
@st.cache_resource
def get_agent():
    db = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}")
    model = ChatGroq(model=MODEL_NAME)
    toolkit = SQLDatabaseToolkit(db=db, llm=model)
    return create_agent(
        model=model,
        tools=[*toolkit.get_tools(), delete_tasks_by_id],
        checkpointer=InMemorySaver(),
        system_prompt=system_prompt,
        # The model occasionally emits malformed tool calls (Groq "tool_use_failed"); retry instead of failing.
        middleware=[ModelRetryMiddleware(max_retries=3, initial_delay=0.5, on_failure="error")],
    )
