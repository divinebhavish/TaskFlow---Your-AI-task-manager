import uuid

import streamlit as st

from core import tasks_db

st.set_page_config(page_title="TaskFlow", page_icon=":material/task_alt:", layout="wide")

tasks_db.init_db()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())


def new_chat():
    st.session_state.messages = []
    st.session_state.thread_id = str(uuid.uuid4())


page = st.navigation(
    [
        st.Page("app_pages/chat.py", title="Assistant", icon=":material/forum:", default=True),
        st.Page("app_pages/board.py", title="Board", icon=":material/view_kanban:"),
        st.Page("app_pages/insights.py", title="Insights", icon=":material/insights:"),
    ],
    position="top",
)

with st.sidebar:
    st.subheader("TaskFlow", icon=":material/task_alt:")
    st.caption("Manage your todos in plain English — backed by SQL.")

    stats = tasks_db.summary(tasks_db.load_tasks())
    with st.container(horizontal=True):
        st.metric("Open", stats["pending"] + stats["in_progress"], border=True)
        st.metric("Done", stats["completed"], border=True)
    st.progress(stats["completion"], text=f"{stats['completion']:.0%} complete")
    if stats["overdue"]:
        st.badge(f"{stats['overdue']} overdue", icon=":material/alarm:", color="red")

    st.space("small")
    st.button("New chat", icon=":material/add_comment:", on_click=new_chat, width="stretch")

page.run()
