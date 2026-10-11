import time

import streamlit as st
from langchain_core.messages import AIMessage, ToolMessage

from core import tasks_db
from core.agent import get_agent

TOOL_LABELS = {
    "sql_db_list_tables": ("Looking up tables", ":material/table_view:"),
    "sql_db_schema": ("Reading table schema", ":material/schema:"),
    "sql_db_query_checker": ("Double-checking the SQL", ":material/fact_check:"),
    "sql_db_query": ("Running SQL query", ":material/database:"),
    "delete_tasks_by_id": ("Deleting tasks", ":material/delete:"),
}
WRITE_KEYWORDS = ("insert", "update", "delete")

SUGGESTIONS = {
    ":violet[:material/add_task:] Add a task": "Add a high priority task 'Finish project report' due tomorrow",
    ":blue[:material/list:] Show my tasks": "Show all my tasks",
    ":orange[:material/hourglass_top:] What's pending?": "What tasks are still pending or in progress?",
    ":red[:material/alarm:] Anything overdue?": "Do I have any overdue tasks?",
    ":green[:material/check_circle:] Mark one done": "Mark my most recent task as completed",
}

AVATARS = {"user": ":material/person:", "assistant": ":material/smart_toy:"}


def render_steps(steps, elapsed):
    label = f"Worked for {elapsed:.1f}s · {len(steps)} step{'s' if len(steps) != 1 else ''}"
    with st.expander(label, type="compact"):
        for step in steps:
            title, icon = TOOL_LABELS.get(step["tool"], (step["tool"], ":material/build:"))
            with st.expander(title, icon=icon, type="step"):
                if step.get("input"):
                    st.code(step["input"], language="sql" if "query" in step["tool"] else None)
                if step.get("output"):
                    st.caption(step["output"])


def tool_input(args):
    if not isinstance(args, dict):
        return str(args)
    return args.get("query") or args.get("table_names") or ", ".join(f"{k}={v}" for k, v in args.items())


def pick_suggestion():
    st.session_state.pending_prompt = SUGGESTIONS[st.session_state.suggestion]
    st.session_state.suggestion = None


def run_agent(prompt):
    """Stream the agent, showing each SQL tool call live. Returns (answer, steps, elapsed)."""
    agent = get_agent()
    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    steps, pending, answer = [], {}, ""
    start = time.perf_counter()

    with st.status(":shimmer[Thinking]", type="compact") as status:
        for update in agent.stream(
            {"messages": [{"role": "user", "content": prompt}]}, config, stream_mode="updates"
        ):
            for node in update.values():
                for msg in (node or {}).get("messages", []):
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        for call in msg.tool_calls:
                            title, icon = TOOL_LABELS.get(call["name"], (call["name"], ":material/build:"))
                            step = {"tool": call["name"], "input": tool_input(call["args"])}
                            box = st.status(title, type="step")
                            if step["input"]:
                                box.code(step["input"], language="sql" if "query" in call["name"] else None)
                            steps.append(step)
                            pending[call["id"]] = (step, box)
                    elif isinstance(msg, ToolMessage):
                        step, box = pending.pop(msg.tool_call_id, (None, None))
                        if step is not None:
                            output = str(msg.content)
                            step["output"] = output[:300] + ("…" if len(output) > 300 else "")
                            box.caption(step["output"])
                            box.update(state="error" if output.startswith("Error") else "complete")
                    elif isinstance(msg, AIMessage):
                        answer = msg.text
        elapsed = time.perf_counter() - start
        status.update(
            label=f"Worked for {elapsed:.1f}s · {len(steps)} step{'s' if len(steps) != 1 else ''}",
            state="complete",
        )
    return answer, steps, elapsed


TABLE_COLORS = {
    "light": {"border": "#c4c4d8", "header": "#ececf7", "stripe": "#f8f8fc", "hover": "#efeffa"},
    "dark": {"border": "#3e3e55", "header": "#23232f", "stripe": "#16161f", "hover": "#24243a"},
}
c = TABLE_COLORS["dark" if st.context.theme.type == "dark" else "light"]
# Give the agent's markdown task tables visible grid lines, a shaded header and striped rows.
st.html(f"""
<style>
[data-testid="stChatMessage"] table {{
    width: 100%; border-collapse: separate; border-spacing: 0;
    border: 1px solid {c['border']}; border-radius: 10px; overflow: hidden;
}}
[data-testid="stChatMessage"] th,
[data-testid="stChatMessage"] td {{
    border: none; border-right: 1px solid {c['border']}; border-bottom: 1px solid {c['border']};
    padding: 10px 14px;
}}
[data-testid="stChatMessage"] th {{ background: {c['header']}; font-weight: 600; }}
[data-testid="stChatMessage"] th:last-child,
[data-testid="stChatMessage"] td:last-child {{ border-right: none; }}
[data-testid="stChatMessage"] tbody tr:last-child td {{ border-bottom: none; }}
[data-testid="stChatMessage"] tbody tr:nth-child(even) td {{ background: {c['stripe']}; }}
[data-testid="stChatMessage"] tbody tr:hover td {{ background: {c['hover']}; }}
</style>
""")

st.title("What's on your plate today?", icon=":material/forum:")
st.caption("Add, update, search and complete tasks just by chatting. Every action runs real SQL on your task database.")

if st.session_state.pop("db_changed_toast", False):
    st.toast("Task board updated", icon=":material/sync:")

for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar=AVATARS.get(message["role"])):
        if message.get("steps"):
            render_steps(message["steps"], message.get("elapsed", 0))
        st.markdown(message["content"])

prompt = st.chat_input(
    "Tell me a task, e.g. “Remind me to call mom on Sunday”", submit_mode="disable"
) or st.session_state.pop("pending_prompt", None)

if not st.session_state.messages and not prompt:
    st.space("small")
    st.pills(
        "Try asking", list(SUGGESTIONS), key="suggestion", on_change=pick_suggestion, label_visibility="collapsed"
    )

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=AVATARS["user"]):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
        try:
            answer, steps, elapsed = run_agent(prompt)
        except Exception as exc:  # network / API key / rate-limit problems
            st.error(f"Something went wrong talking to the model: {exc}", icon=":material/error:")
            st.session_state.messages.pop()
            st.stop()
        st.markdown(answer or "_(no response)_")

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "steps": steps, "elapsed": elapsed}
    )
    if any(
        s["tool"] == "delete_tasks_by_id"
        or (s["tool"] == "sql_db_query" and s["input"].lstrip().lower().startswith(WRITE_KEYWORDS))
        for s in steps
    ):
        # Safety net in case the model deleted via raw SQL, then rerun so the sidebar stats pick up the change.
        tasks_db.renumber_ids()
        st.session_state.db_changed_toast = True
        st.rerun()
