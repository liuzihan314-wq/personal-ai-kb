"""Single-page Streamlit MVP for the personal AI knowledge base."""

from collections.abc import Sequence
from typing import Any

import streamlit as st

from pkb.ui.services import (
    IngestResult,
    UIService,
    can_generate_script,
    find_candidate,
)


_STATE_DEFAULTS: dict[str, Any] = {
    "last_ingest": None,
    "search_result": None,
    "qa_result": None,
    "knowledge_result": None,
    "topics_result": None,
    "script_result": None,
    "topic_widget_previous": None,
    "topic_selection_confirmed": False,
}


def _init_state() -> None:
    for key, value in _STATE_DEFAULTS.items():
        st.session_state.setdefault(key, value)


def _show_error(error: Exception) -> None:
    message = str(error).strip() or error.__class__.__name__
    st.error(message)


def _render_ingest_result(result: IngestResult | None) -> None:
    if result is None:
        return
    document = result.document
    st.success(f"已保存：{document.title or document.id}")
    columns = st.columns(3)
    columns[0].metric("Raw ID", document.id[:12])
    columns[1].metric("Note", "已生成" if result.note else "未生成")
    columns[2].metric("Index", f"{len(result.index.entries)} 条")
    st.caption(f"Raw：{document.original_file or '本地记录'}")
    st.caption(f"Note：{result.note.path}")


def _render_retrieval(result: Any, *, heading: str = "检索结果") -> None:
    if result is None:
        return
    st.subheader(heading)
    st.caption(f"状态：{result.status} · 候选：{len(result.candidates)}")
    if not result.candidates:
        st.info("没有命中本地 Index。")
        return
    for rank, candidate in enumerate(result.candidates, start=1):
        with st.expander(f"{rank}. {candidate.title} · {candidate.score:.3f}"):
            st.caption(f"document_id：{candidate.document_id}")
            st.caption(f"Note：{candidate.note_path}")
            if candidate.evidence.matched_fields:
                st.write(
                    "匹配字段："
                    + "、".join(candidate.evidence.matched_fields),
                )
            for reason in candidate.reasons:
                st.caption(f"{reason.field}：{reason.explanation}")


def _render_sources(sources: Sequence[Any]) -> None:
    if not sources:
        st.caption("暂无可展示的来源链。")
        return
    st.markdown("**来源链**")
    for source in sources:
        location = source.path or source.reference or source.source_id
        availability = "可读取" if source.available else "不可读取"
        title = source.title or source.source_id
        st.caption(f"{source.kind} · {title} · {availability} · {location}")


def _render_import_tab(service: UIService) -> None:
    st.subheader("导入资料")
    st.caption("导入后会调用已有 Note Service，并重建本地 JSON Index。")
    with st.form("pdf_import_form", clear_on_submit=True):
        uploaded = st.file_uploader("选择文本型 PDF", type=["pdf"])
        submitted = st.form_submit_button("导入 PDF")
    if submitted:
        if uploaded is None:
            st.warning("请先选择一个 PDF 文件。")
        else:
            try:
                st.session_state["last_ingest"] = service.import_pdf(
                    uploaded.name,
                    uploaded.getvalue(),
                )
            except Exception as error:
                _show_error(error)
    _render_ingest_result(st.session_state["last_ingest"])

    st.subheader("添加观点卡片")
    with st.form("idea_form", clear_on_submit=True):
        idea_content = st.text_area("观点 / 好句 / 灵感", height=130)
        idea_source = st.text_input("来源 URL（可选）")
        idea_tags = st.text_input("标签（可选，用逗号分隔）")
        idea_note = st.text_area("个人备注（可选）", height=90)
        submitted = st.form_submit_button("保存观点卡片")
    if submitted:
        try:
            st.session_state["last_ingest"] = service.add_idea(
                idea_content,
                source_url=idea_source or None,
                tags=idea_tags.split(",") if idea_tags else None,
                note=idea_note or None,
            )
        except Exception as error:
            _show_error(error)
    _render_ingest_result(st.session_state["last_ingest"])


def _render_search_qa_tab(service: UIService) -> None:
    st.subheader("Search")
    with st.form("search_form"):
        query = st.text_input("检索词")
        limit = st.number_input("最多返回", min_value=1, max_value=50, value=10, step=1)
        submitted = st.form_submit_button("检索")
    if submitted:
        try:
            st.session_state["search_result"] = service.search(
                query,
                limit=int(limit),
            )
        except Exception as error:
            _show_error(error)
    _render_retrieval(st.session_state["search_result"])

    st.subheader("Q&A")
    with st.form("qa_form"):
        question = st.text_area("问题", height=100)
        qa_limit = st.number_input(
            "最多使用的候选",
            min_value=1,
            max_value=50,
            value=10,
            step=1,
            key="qa_limit",
        )
        submitted = st.form_submit_button("回答")
    if submitted:
        try:
            st.session_state["qa_result"] = service.answer(
                question,
                limit=int(qa_limit),
            )
        except Exception as error:
            _show_error(error)
    result = st.session_state["qa_result"]
    if result is not None:
        st.subheader("回答")
        st.caption(f"状态：{result.status} · 证据级别：{result.evidence_level}")
        if result.answer:
            st.markdown(result.answer)
        else:
            st.info(result.reason)
        _render_sources(result.sources)
        for evidence in result.evidence:
            st.caption(f"{evidence.source_kind}：{evidence.explanation}")


def _render_synthesis_tab(service: UIService) -> None:
    st.subheader("Topic synthesis")
    st.caption("按输入主题调用 Knowledge Compiler，默认使用当前所有本地 Notes。")
    with st.form("synthesis_form"):
        topic = st.text_input("主题")
        submitted = st.form_submit_button("生成主题综合")
    if submitted:
        try:
            st.session_state["knowledge_result"] = service.synthesize_topic(topic)
        except Exception as error:
            _show_error(error)
    result = st.session_state["knowledge_result"]
    if result is not None:
        st.success(f"主题页已保存：{result.knowledge.topic}")
        st.markdown(result.knowledge.current_synthesis)
        st.caption(f"Knowledge：{result.path}")
        st.markdown("**来源链**")
        for source in result.knowledge.sources:
            st.caption(
                f"note · {source.title or source.note_id} · "
                f"{source.reference or source.note_id}",
            )


def _render_candidate(candidate: Any, rank: int) -> None:
    with st.expander(f"{rank}. {candidate.title} · {candidate.score:.3f}"):
        st.write(candidate.why_worth_doing)
        for reason in candidate.reasons:
            st.caption(f"{reason.rule}：{reason.explanation}")
        for evidence in candidate.evidence:
            st.caption(f"{evidence.signal}：{', '.join(evidence.values)}")
        for source in candidate.sources:
            st.caption(f"来源 {source.kind}：{source.title or source.source_id} · {source.path}")


def _render_topics_tab(service: UIService) -> None:
    st.subheader("Generate topics")
    st.caption("候选来自本地 Index、Notes 和 Topic Knowledge；不会自动生成口播。")
    if st.button("生成选题", key="generate_topics_button"):
        try:
            st.session_state["topics_result"] = service.generate_topics(limit=5)
            st.session_state["script_result"] = None
            st.session_state["topic_selection_confirmed"] = False
            st.session_state["topic_widget_previous"] = None
            st.session_state["topic_select"] = ""
        except Exception as error:
            _show_error(error)

    topics_result = st.session_state["topics_result"]
    if topics_result is None:
        st.info("点击“生成选题”后查看候选。")
        return
    st.info(topics_result.message)
    for rank, candidate in enumerate(topics_result.candidates, start=1):
        _render_candidate(candidate, rank)
    if not topics_result.candidates:
        return

    titles = ["", *[candidate.title for candidate in topics_result.candidates]]
    selected_title = st.selectbox(
        "明确选择一个候选",
        titles,
        format_func=lambda value: value or "请选择候选选题",
        key="topic_select",
    )
    previous = st.session_state["topic_widget_previous"]
    if selected_title != previous:
        st.session_state["topic_selection_confirmed"] = False
        st.session_state["topic_widget_previous"] = selected_title

    candidate = find_candidate(topics_result.candidates, selected_title)
    if st.button(
        "确认此选题",
        disabled=candidate is None,
        key="confirm_topic_button",
    ):
        st.session_state["topic_selection_confirmed"] = True
        st.session_state["script_result"] = None
        st.success(f"已确认：{selected_title}")

    confirmed = st.session_state["topic_selection_confirmed"]
    allowed = can_generate_script(
        topics_result.candidates,
        selected_title,
        confirmed,
    )
    if not allowed:
        st.warning("请先从候选中选择并点击“确认此选题”，再生成口播。")
    if st.button(
        "生成口播",
        disabled=not allowed,
        key="generate_script_button",
    ) and allowed:
        assert candidate is not None
        try:
            st.session_state["script_result"] = service.write_script(
                candidate,
                confirmed=True,
            )
        except Exception as error:
            _show_error(error)

    script_result = st.session_state["script_result"]
    if script_result is None:
        return
    st.subheader("口播结果")
    if script_result.script:
        st.success(script_result.message)
        st.text_area("口播稿", value=script_result.script_text, height=360)
    else:
        st.warning(script_result.message)
    _render_retrieval(script_result.retrieval, heading="二次检索")
    _render_sources(script_result.sources)
    for evidence in script_result.evidence:
        st.caption(f"{evidence.source_kind}：{evidence.explanation}")


def main(service: UIService | None = None) -> None:
    """Render the single-page application."""

    st.set_page_config(
        page_title="Personal AI Knowledge Base",
        page_icon="🗂️",
        layout="wide",
    )
    _init_state()
    active_service = service or UIService()

    st.title("个人 AI 知识库")
    st.caption("本地可追溯工作台：资料 → 观点 → 检索 / 综合 → 选题 → 口播")
    with st.sidebar:
        st.subheader("运行信息")
        st.caption(f"数据目录：{active_service.paths.data_dir}")
        st.caption("V1 使用本地文件、Mock Provider 和 JSON Index。")

    import_tab, search_tab, synthesis_tab, topics_tab = st.tabs(
        ["导入与观点", "Search / Q&A", "Topic synthesis", "选题与口播"],
    )
    with import_tab:
        _render_import_tab(active_service)
    with search_tab:
        _render_search_qa_tab(active_service)
    with synthesis_tab:
        _render_synthesis_tab(active_service)
    with topics_tab:
        _render_topics_tab(active_service)


if __name__ == "__main__":
    main()
