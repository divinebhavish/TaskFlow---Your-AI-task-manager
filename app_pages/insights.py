from datetime import date

import streamlit as st

from core import tasks_db
from core.tasks_db import PRIORITIES, STATUS_LABELS, STATUSES

st.title("Insights", icon=":material/insights:")
st.caption("A quick look at how your tasks are moving.")

tasks = tasks_db.load_tasks()
stats = tasks_db.summary(tasks)

with st.container(horizontal=True, gap="medium"):
    st.metric("Total tasks", stats["total"], border=True)
    st.metric("Pending", stats["pending"], border=True)
    st.metric("In progress", stats["in_progress"], border=True)
    st.metric("Completed", stats["completed"], border=True)
    st.metric("Completion rate", f"{stats['completion']:.0%}", border=True)
    st.metric("Overdue", stats["overdue"], border=True,
              delta="needs attention" if stats["overdue"] else None, delta_color="inverse")

if tasks.empty:
    st.info("Charts will appear once you've added a few tasks.", icon=":material/bar_chart:")
    st.stop()

left, right = st.columns(2, gap="medium")

with left.container(border=True):
    st.markdown("**Tasks by status**")
    by_status = (
        tasks["status"].value_counts().reindex(STATUSES, fill_value=0)
        .rename(index=STATUS_LABELS).rename_axis("Status").reset_index(name="Tasks")
    )
    st.bar_chart(by_status, x="Status", y="Tasks", horizontal=True, height=220, sort=False,
                 alt="Bar chart of task counts by status")

with right.container(border=True):
    st.markdown("**Open tasks by priority**")
    open_tasks = tasks[tasks["status"] != "completed"]
    by_priority = (
        open_tasks["priority"].value_counts().reindex(PRIORITIES, fill_value=0)
        .rename(index=str.capitalize).rename_axis("Priority").reset_index(name="Tasks")
    )
    st.bar_chart(by_priority, x="Priority", y="Tasks", horizontal=True, height=220, sort=False,
                 alt="Bar chart of open task counts by priority")

with st.container(border=True):
    st.markdown("**Tasks created per day**")
    created = tasks.dropna(subset=["created_at"])
    per_day = (
        created.set_index("created_at").resample("D")["id"].count()
        .rename_axis("Day").reset_index(name="Tasks created")
    )
    st.bar_chart(per_day, x="Day", y="Tasks created", height=240, alt="Bar chart of tasks created per day")

upcoming = tasks[(tasks["status"] != "completed") & tasks["due_date"].notna()].sort_values("due_date")
if not upcoming.empty:
    st.subheader("Upcoming deadlines", icon=":material/event_upcoming:")
    upcoming = upcoming.assign(days_left=upcoming["due_date"].apply(lambda d: (d - date.today()).days))
    st.dataframe(
        upcoming[["title", "status", "priority", "due_date", "days_left"]].head(10),
        hide_index=True,
        column_config={
            "title": "Title",
            "status": st.column_config.TextColumn("Status"),
            "priority": "Priority",
            "due_date": st.column_config.DateColumn("Due", format="DD MMM YYYY"),
            "days_left": st.column_config.NumberColumn("Days left", format="%d d"),
        },
        alt="Table of upcoming task deadlines",
    )
