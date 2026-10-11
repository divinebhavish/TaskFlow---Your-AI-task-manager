from datetime import date

import pandas as pd
import streamlit as st

from core import tasks_db
from core.tasks_db import PRIORITIES, PRIORITY_COLORS, STATUS_COLORS, STATUS_ICONS, STATUS_LABELS, STATUSES

if "editor_version" not in st.session_state:
    st.session_state.editor_version = 0


@st.dialog("New task", icon=":material/add_task:")
def new_task_dialog():
    with st.form("new_task", border=False):
        title = st.text_input("Title", placeholder="What needs to be done?")
        description = st.text_area("Description", placeholder="Optional details", height=90)
        with st.container(horizontal=True):
            status = st.selectbox("Status", STATUSES, format_func=STATUS_LABELS.get)
            priority = st.selectbox("Priority", PRIORITIES, index=1, format_func=str.capitalize)
        due = st.date_input("Due date", value=None, min_value=date(2000, 1, 1))
        if st.form_submit_button("Create task", icon=":material/add:", type="primary", width="stretch"):
            if not title.strip():
                st.error("Please give the task a title.", icon=":material/error:")
                return
            tasks_db.add_task(title.strip(), description.strip(), status, priority, due)
            st.toast(f"Added “{title.strip()}”", icon=":material/check_circle:")
            st.rerun()


def apply_table_edits():
    """Write data_editor changes (edits, added rows, deleted rows) back to the database."""
    key = f"board_editor_{st.session_state.editor_version}"
    changes = st.session_state.get(key, {})
    shown = st.session_state.board_shown

    for row_idx, edits in changes.get("edited_rows", {}).items():
        tasks_db.update_task(shown.iloc[int(row_idx)]["id"], **edits)
    for row in changes.get("added_rows", []):
        if str(row.get("title") or "").strip():
            tasks_db.add_task(
                row["title"].strip(),
                row.get("description") or "",
                row.get("status") or "pending",
                row.get("priority") or "medium",
                row.get("due_date"),
            )
    deleted = [shown.iloc[int(i)]["id"] for i in changes.get("deleted_rows", [])]
    if deleted:
        tasks_db.delete_tasks(deleted)

    # A fresh key resets the editor so stale row indices are never re-applied.
    st.session_state.editor_version += 1
    st.toast("Changes saved", icon=":material/save:")


def move_task(task_id, status):
    tasks_db.update_task(task_id, status=status)


def remove_task(task_id):
    tasks_db.delete_tasks([task_id])
    st.toast("Task deleted", icon=":material/delete:")


def due_label(due, status):
    if due is None or pd.isna(due):
        return None
    days = (due - date.today()).days
    if status != "completed" and days < 0:
        return f":red-badge[:material/alarm: {abs(days)}d overdue]"
    if days == 0:
        return ":orange-badge[:material/today: Today]"
    if days == 1:
        return ":blue-badge[:material/event: Tomorrow]"
    return f":gray-badge[:material/event: {due:%d %b}]"


def task_card(task):
    with st.container(border=True, gap="small"):
        st.markdown(f":gray[#{task['id']}] **{task['title']}**")
        if task["description"]:
            st.caption(task["description"])
        badges = [f":{PRIORITY_COLORS[task['priority']]}-badge[{task['priority'].capitalize()}]"]
        if label := due_label(task["due_date"], task["status"]):
            badges.append(label)
        st.markdown(" ".join(badges))

        idx = STATUSES.index(task["status"])
        with st.container(horizontal=True, gap="small"):
            if idx > 0:
                st.button(
                    "", icon=":material/arrow_back:", key=f"back_{task['id']}", help=f"Move to {STATUS_LABELS[STATUSES[idx - 1]]}",
                    on_click=move_task, args=(task["id"], STATUSES[idx - 1]), type="tertiary",
                )
            if idx < len(STATUSES) - 1:
                st.button(
                    "", icon=":material/arrow_forward:", key=f"fwd_{task['id']}", help=f"Move to {STATUS_LABELS[STATUSES[idx + 1]]}",
                    on_click=move_task, args=(task["id"], STATUSES[idx + 1]), type="tertiary",
                )
            st.space("stretch")
            st.button(
                "", icon=":material/delete:", key=f"del_{task['id']}", help="Delete task",
                on_click=remove_task, args=(task["id"],), type="tertiary",
            )


with st.container(horizontal=True, vertical_alignment="bottom"):
    st.title("Task board", icon=":material/view_kanban:", width="content")
    st.space("stretch")
    if st.button("New task", icon=":material/add:", type="primary"):
        new_task_dialog()

tasks = tasks_db.load_tasks()

with st.container(horizontal=True, vertical_alignment="bottom", gap="medium"):
    search = st.text_input(
        "Search", placeholder="Search tasks…", icon=":material/search:", label_visibility="collapsed", width=280
    )
    priority_filter = st.pills(
        "Priority", PRIORITIES, selection_mode="multi", format_func=str.capitalize, label_visibility="collapsed"
    )
    st.space("stretch")
    view = st.segmented_control(
        "View",
        ["Kanban", "Table"],
        default="Kanban",
        format_func=lambda v: f":material/{'view_kanban' if v == 'Kanban' else 'table_rows'}: {v}",
        label_visibility="collapsed",
        key="board_view",
    )

shown = tasks
if search:
    needle = search.lower()
    shown = shown[
        shown["title"].str.lower().str.contains(needle, regex=False)
        | shown["description"].fillna("").str.lower().str.contains(needle, regex=False)
    ]
if priority_filter:
    shown = shown[shown["priority"].isin(priority_filter)]
shown = shown.reset_index(drop=True)

if tasks.empty:
    st.space("medium")
    st.info(
        "No tasks yet. Click **New task**, or ask the assistant something like *“Add a task to buy groceries tomorrow”*.",
        icon=":material/inbox:",
    )
elif view == "Table":
    st.session_state.board_shown = shown
    st.data_editor(
        shown,
        key=f"board_editor_{st.session_state.editor_version}",
        on_change=apply_table_edits,
        num_rows="dynamic",
        hide_index=True,
        column_order=["id", "title", "description", "status", "priority", "due_date", "created_at"],
        column_config={
            "id": st.column_config.NumberColumn("No.", disabled=True, width="small"),
            "title": st.column_config.TextColumn("Title", required=True, width="medium"),
            "description": st.column_config.TextColumn("Description", width="large"),
            "status": st.column_config.SelectboxColumn(
                "Status", options=STATUSES, required=True, default="pending",
                format_func=lambda s: STATUS_LABELS.get(s, s),
            ),
            "priority": st.column_config.SelectboxColumn(
                "Priority", options=PRIORITIES, required=True, default="medium", format_func=str.capitalize
            ),
            "due_date": st.column_config.DateColumn("Due", format="DD MMM YYYY"),
            "created_at": st.column_config.DatetimeColumn("Created", format="DD MMM, HH:mm", disabled=True),
        },
        alt="Editable table of tasks",
    )
    with st.container(horizontal=True):
        st.caption(":material/info: Edit cells directly, add rows at the bottom, or select rows and press Delete. Changes save instantly.")
        st.space("stretch")
        st.download_button(
            "Export CSV", shown.to_csv(index=False), file_name="tasks.csv", mime="text/csv",
            icon=":material/download:", type="tertiary",
        )
else:
    columns = st.columns(len(STATUSES), gap="medium")
    for column, status in zip(columns, STATUSES):
        group = shown[shown["status"] == status]
        with column:
            st.markdown(
                f"#### :{STATUS_COLORS[status]}[{STATUS_ICONS[status]}] {STATUS_LABELS[status]} "
                f":gray-badge[{len(group)}]"
            )
            if group.empty:
                st.caption("Nothing here")
            for _, task in group.iterrows():
                task_card(task)
