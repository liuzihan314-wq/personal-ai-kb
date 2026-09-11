"""Standalone Streamlit entry point for the project roadmap dashboard."""

from datetime import datetime
from html import escape

import streamlit as st

from pkb.ui.roadmap import RoadmapTask, load_roadmap, project_roadmap_path


_DASHBOARD_CSS = """
<style>
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] { background: #f7f5f1 !important; }
header[data-testid="stHeader"] { background: transparent !important; }
main .block-container { max-width: 1080px; padding-top: 3rem; background: #f7f5f1 !important; }
.roadmap-kicker { color: #6046bb; font-size: .76rem; font-weight: 850; letter-spacing: .14em; }
.roadmap-heading { color: #25212d !important; font-size: 2.55rem; margin: .3rem 0; }
.roadmap-copy { color: #544e5c !important; font-size: .96rem; margin-bottom: 1.15rem; }
.roadmap-status { display: inline-block; margin-bottom: .6rem; padding: .32rem .64rem; border-radius: 999px; font-size: .72rem; font-weight: 850; letter-spacing: .06em; }
.status-done { background: #dcefe4; color: #266744; }
.status-ready { background: #e5dfff; color: #5637b7; }
.status-in-progress { background: #d9eef9; color: #176083; }
.status-review { background: #fff0c8; color: #795207; }
.status-blocked { background: #f9dede; color: #a33a42; }
.status-poc-required { background: #f6dfeb; color: #8d3564; }
.status-backlog { background: #e9e6e1; color: #5c5650; }
[data-testid="stMetric"] { border: 1px solid #e5dfd7; border-radius: 1rem; padding: .85rem 1rem; background: #fffefa; }
[data-testid="stMetric"] * { color: #25212d !important; }
[data-testid="stExpander"] { border-color: #ded8d0; background: #fffefa; }
[data-testid="stExpander"] summary p, [data-testid="stExpander"] [data-testid="stMarkdownContainer"] { color: #25212d !important; }
[data-testid="stCaptionContainer"] { color: #544e5c !important; }
[data-testid="stSelectbox"] label, [data-testid="stProgress"] [data-testid="stMarkdownContainer"] { color: #25212d !important; }
</style>
"""


def _status_class(status: str) -> str:
    return f"status-{status.lower().replace('_', '-')}"


def _render_task(task: RoadmapTask) -> None:
    dependencies = "、".join(task.dependencies) if task.dependencies else "无前置任务"
    with st.expander(f"{task.task_id}｜{task.title}", expanded=task.status != "DONE"):
        st.markdown(
            f'<span class="roadmap-status {_status_class(task.status)}">{escape(task.status)}</span>',
            unsafe_allow_html=True,
        )
        st.caption(f"依赖：{dependencies}")
        if task.owner:
            st.caption(f"负责人：{task.owner}")
        if task.annotation:
            st.markdown("**任务说明 / 最近记录**")
            st.write(task.annotation)
        else:
            st.caption("ROADMAP.md 尚未记录任务说明或进展。")


def _render_dashboard() -> None:
    try:
        tasks = load_roadmap()
    except OSError as error:
        st.error(f"无法读取 ROADMAP.md：{error}")
        return

    total = len(tasks)
    done = sum(task.status == "DONE" for task in tasks)
    active = sum(task.status in {"READY", "IN_PROGRESS", "REVIEW", "POC_REQUIRED"} for task in tasks)
    blocked = sum(task.status == "BLOCKED" for task in tasks)
    updated_at = datetime.fromtimestamp(project_roadmap_path().stat().st_mtime)

    st.markdown('<div class="roadmap-kicker">PROJECT ROADMAP</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="roadmap-heading">项目进度</h1>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="roadmap-copy">仅在 MAIN 验收任务并更新 ROADMAP.md 后同步。上次文件更新时间：{updated_at:%Y-%m-%d %H:%M:%S}</p>',
        unsafe_allow_html=True,
    )
    st.progress(done / total if total else 0, text=f"已完成 {done} / {total} 个任务")
    metrics = st.columns(4)
    metrics[0].metric("总任务", total)
    metrics[1].metric("已完成", done)
    metrics[2].metric("可推进", active)
    metrics[3].metric("受阻", blocked)

    statuses = ["全部", *sorted({task.status for task in tasks})]
    selected_status = st.selectbox("筛选状态", statuses)
    visible_tasks = tasks if selected_status == "全部" else [task for task in tasks if task.status == selected_status]
    st.caption(f"当前显示 {len(visible_tasks)} 个任务。状态与任务说明均来自 ROADMAP.md。")
    for task in visible_tasks:
        _render_task(task)


def main() -> None:
    """Render the roadmap without the knowledge-base workspace controls."""

    st.set_page_config(
        page_title="项目进度｜Personal AI Knowledge Base",
        page_icon="▣",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(_DASHBOARD_CSS, unsafe_allow_html=True)
    _render_dashboard()


if __name__ == "__main__":
    main()
