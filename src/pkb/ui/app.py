"""Single-page Streamlit MVP for the personal AI knowledge base."""

from collections.abc import Sequence
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import streamlit as st
import streamlit.components.v1 as components

from pkb.auth import (
    AuthError,
    AuthenticationError,
    CloudflareAccessAuthenticator,
    IdentityContext,
    LocalAuthenticator,
)
from pkb.config import get_settings, save_local_settings
from pkb.retrieval import EmbeddingRequestError
from pkb.ui.services import (
    IngestResult,
    UIService,
    can_generate_script,
    find_candidate,
)
from pkb.ui.styles import THEME_CSS


_STATE_DEFAULTS: dict[str, Any] = {
    "last_ingest": None,
    "wechat_import_result": None,
    "search_result": None,
    "qa_result": None,
    "knowledge_result": None,
    "topics_result": None,
    "script_result": None,
    "topic_widget_previous": None,
    "topic_selection_confirmed": False,
    "provider_session": None,
    "embedding_session": None,
}

_INGEST_INVALIDATED_STATE = (
    "search_result",
    "qa_result",
    "knowledge_result",
    "topics_result",
    "script_result",
    "topic_widget_previous",
)

_CLOUDFLARE_LOGOUT_PATH = "/cdn-cgi/access/logout"
_LOCAL_IDENTITY_STATE_KEY = "_local_identity"


def _init_state() -> None:
    for key, value in _STATE_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    # Drop a pre-title generated result kept by an older Streamlit session.
    # Otherwise the page can continue displaying the obsolete retrieval-style copy.
    script_result = st.session_state.get("script_result")
    if (
        getattr(script_result, "status", None) == "generated"
        and not hasattr(script_result, "title")
    ):
        st.session_state["script_result"] = None


def _invalidate_results_after_ingest(state: Any) -> None:
    """Discard page results that were produced from the previous Index."""

    for key in _INGEST_INVALIDATED_STATE:
        state[key] = None
    state["topic_selection_confirmed"] = False


def _show_error(error: Exception) -> None:
    message = str(error).strip() or error.__class__.__name__
    st.error(message)


def _identity_for_settings(
    settings: Any,
    headers: Any | None = None,
) -> IdentityContext | None:
    """Resolve V2 identity only when authentication is explicitly enabled."""

    if not settings.auth_enabled:
        return None
    if headers is None:
        try:
            request_headers = st.context.headers
        except (AttributeError, RuntimeError) as error:
            raise AuthenticationError(
                "headers_unavailable",
                "当前 Streamlit 版本无法读取认证请求头",
            ) from error
    else:
        request_headers = headers
    return CloudflareAccessAuthenticator.from_settings(settings).authenticate_headers(
        request_headers
    )


def _html(value: object) -> str:
    """Escape values interpolated into the static presentation HTML."""

    return escape(str(value), quote=True)


def _render_theme() -> None:
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def _install_translation_guard() -> None:
    """Prevent browser translation from mutating Streamlit's React DOM."""

    components.html(
        """
        <script>
        (() => {
          try {
            const doc = window.parent.document;
            const root = doc.documentElement;
            root.lang = "zh-CN";
            root.setAttribute("translate", "no");
            root.classList.add("notranslate");
            let meta = doc.head.querySelector('meta[name="google"]');
            if (!meta) {
              meta = doc.createElement("meta");
              meta.name = "google";
              doc.head.appendChild(meta);
            }
            meta.content = "notranslate";
          } catch (_error) {
            // The app remains usable if a browser blocks parent-frame access.
          }
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def _render_brand_header() -> None:
    st.markdown(
        """
        <section class="pkb-hero" aria-label="Personal AI Knowledge Base">
            <div class="pkb-hero-copy">
                <div class="pkb-kicker">Personal AI Knowledge Base</div>
                <h1>把零散灵感，<br>变成可用知识。</h1>
                <p>一个本地优先、可追溯的知识工作台。把资料、观点和问题放在同一条流里，最后沉淀成可以继续使用的主题与口播。</p>
                <div class="pkb-hero-tags">
                    <span>Local first</span>
                    <span>Traceable</span>
                    <span>From notes to output</span>
                </div>
            </div>
            <div class="pkb-hero-art" aria-hidden="true">
                <div class="pkb-orbit"></div>
                <div class="pkb-orbit-core">✦</div>
                <div class="pkb-orbit-note">Notes → Knowledge → Voice</div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_flow_overview() -> None:
    st.markdown(
        """
        <div class="pkb-flow-grid" aria-label="工作流概览">
            <article class="pkb-flow-card">
                <div class="pkb-flow-top"><span>01 / Capture</span><span class="pkb-flow-icon">↳</span></div>
                <h3>导入与观点</h3>
                <p>PDF 与灵感卡片，进入本地资料流。</p>
            </article>
            <article class="pkb-flow-card">
                <div class="pkb-flow-top"><span>02 / Explore</span><span class="pkb-flow-icon">⌕</span></div>
                <h3>Search / Q&amp;A</h3>
                <p>从来源链里找到答案与证据。</p>
            </article>
            <article class="pkb-flow-card">
                <div class="pkb-flow-top"><span>03 / Distill</span><span class="pkb-flow-icon">✦</span></div>
                <h3>Topic synthesis</h3>
                <p>把多篇 Note 编译成主题知识。</p>
            </article>
            <article class="pkb-flow-card">
                <div class="pkb-flow-top"><span>04 / Publish</span><span class="pkb-flow-icon">↗</span></div>
                <h3>选题与口播</h3>
                <p>先确认选题，再生成可追溯口播。</p>
            </article>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _provider_session_values() -> dict[str, str] | None:
    """Return the current browser-only provider settings, if applied."""

    values = st.session_state.get("provider_session")
    if not isinstance(values, dict):
        return None
    required = ("provider_name", "model", "base_url", "api_key")
    if not all(isinstance(values.get(key), str) for key in required):
        return None
    return {key: values[key] for key in required}


def _embedding_session_values() -> dict[str, str] | None:
    """Return independent browser-only Embedding settings, if applied."""

    values = st.session_state.get("embedding_session")
    if not isinstance(values, dict):
        return None
    required = ("embedding_model", "embedding_base_url", "embedding_api_key")
    if not all(isinstance(values.get(key), str) for key in required):
        return None
    return {key: values[key] for key in required}


def _saved_provider_values() -> dict[str, str] | None:
    """Return local Provider settings for pre-filling non-secret fields."""

    settings = get_settings()
    api_key = settings.ai_api_key.get_secret_value() if settings.ai_api_key else ""
    values = {
        "provider_name": settings.ai_provider or "",
        "model": settings.ai_model or "",
        "base_url": settings.ai_base_url or "",
        "api_key": api_key,
    }
    return values if all(values.values()) else None


def _saved_embedding_values() -> dict[str, str] | None:
    """Return local Embedding settings for pre-filling non-secret fields."""

    settings = get_settings()
    api_key = (
        settings.embedding_api_key.get_secret_value()
        if settings.embedding_api_key
        else ""
    )
    values = {
        "embedding_model": settings.embedding_model or "",
        "embedding_base_url": settings.embedding_base_url or "",
        "embedding_api_key": api_key,
    }
    return values if all(values.values()) else None


def _render_provider_configuration() -> None:
    """Render the local Provider configuration form without exposing its key."""

    current = _provider_session_values() or _saved_provider_values() or {}
    saved = _saved_provider_values() is not None
    with st.expander("AI 服务设置", expanded=not bool(current)):
        if saved:
            st.success("已从本机 .env 加载。重启电脑或关闭网页后仍会自动使用。")
        st.caption("保存后写入本项目根目录的本机 .env；密钥不显示、不写日志，也不会提交到 Git。")
        with st.form("provider_configuration_form"):
            provider_label = st.selectbox(
                "服务商",
                ["DeepSeek", "OpenAI 兼容服务"],
                index=0 if current.get("provider_name", "deepseek") == "deepseek" else 1,
            )
            model = st.text_input(
                "模型",
                value=current.get("model", "deepseek-v4-flash"),
                placeholder="例如：deepseek-v4-flash",
            )
            base_url = st.text_input(
                "接口地址",
                value=current.get("base_url", "https://api.deepseek.com"),
                placeholder="https://api.deepseek.com",
            )
            api_key = st.text_input(
                "API 密钥",
                type="password",
                value="",
                placeholder="粘贴你的 API Key",
            )
            apply = st.form_submit_button("保存到本机并应用", use_container_width=True)
        if apply:
            provider_key = api_key.strip() or current.get("api_key", "")
            if not all(value.strip() for value in (model, base_url, provider_key)):
                st.warning("请填写模型、接口地址和 API 密钥。")
            else:
                session_values = {
                    "provider_name": "deepseek"
                    if provider_label == "DeepSeek"
                else "openai-compatible",
                    "model": model.strip(),
                    "base_url": base_url.strip(),
                    "api_key": provider_key,
                }
                save_local_settings(
                    {
                        "PKB_AI_PROVIDER": session_values["provider_name"],
                        "PKB_AI_MODEL": session_values["model"],
                        "PKB_AI_BASE_URL": session_values["base_url"],
                        "PKB_AI_API_KEY": session_values["api_key"],
                    }
                )
                st.session_state["provider_session"] = session_values
                st.success("已保存到本机，之后会自动加载。")


def _render_embedding_configuration() -> None:
    """Render the local Embedding configuration form without exposing its key."""

    current = _embedding_session_values() or _saved_embedding_values() or {}
    saved = _saved_embedding_values() is not None
    embedding_keys = ("embedding_model", "embedding_base_url", "embedding_api_key")
    enabled = all(current.get(key, "").strip() for key in embedding_keys)
    with st.expander("语义检索 / DashScope Embedding", expanded=not enabled):
        if enabled:
            st.success("当前已启用 DashScope 语义检索。")
        else:
            st.info("当前为仅直接检索；配置后才会启用语义向量召回。")
        if saved:
            st.caption("配置已从本机 .env 自动加载。")
        else:
            st.caption("保存后写入本项目根目录的本机 .env；密钥不显示、不写日志，也不会提交到 Git。")
        with st.form("embedding_configuration_form"):
            model = st.text_input(
                "Embedding 模型",
                value=current.get("embedding_model", "qwen3.7-text-embedding-flash"),
            )
            base_url = st.text_input(
                "Embedding Base URL",
                value=current.get("embedding_base_url", ""),
                placeholder="https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            )
            api_key = st.text_input(
                "Embedding API Key",
                type="password",
                value="",
                placeholder="粘贴 Embedding API Key",
            )
            apply = st.form_submit_button("保存语义检索配置", use_container_width=True)
        if apply:
            key = api_key.strip() or current.get("embedding_api_key", "")
            values = (model.strip(), base_url.strip(), key)
            if not any(values):
                st.session_state["embedding_session"] = None
                st.info("当前为仅直接检索。")
            elif not all(values):
                st.warning("请同时填写 Embedding 模型、Base URL 和 API Key。")
            else:
                st.session_state["embedding_session"] = {
                    "embedding_model": values[0],
                    "embedding_base_url": values[1],
                    "embedding_api_key": values[2],
                }
                save_local_settings(
                    {
                        "PKB_EMBEDDING_MODEL": values[0],
                        "PKB_EMBEDDING_BASE_URL": values[1],
                        "PKB_EMBEDDING_API_KEY": values[2],
                    }
                )
                # Saved settings are the durable source of truth.  Dropping a
                # previous browser-only binding prevents an old endpoint from
                # overriding the just-saved configuration on later searches.
                st.session_state["embedding_session"] = None
                st.success("已保存到本机，已重新加载语义检索配置。")


def _local_identity_from_session(
    session_state: Any | None = None,
) -> IdentityContext | None:
    """Return the local identity stored in this browser session, if any."""

    state = st.session_state if session_state is None else session_state
    identity = state.get(_LOCAL_IDENTITY_STATE_KEY)
    if isinstance(identity, IdentityContext):
        return identity
    return None


def _render_local_login(settings: Any) -> None:
    """Render the no-domain local username/password login gate."""

    with st.form("local_login"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录")
    if not submitted:
        return
    if not username or not password:
        st.error("请输入用户名和密码。")
        return

    authenticator = LocalAuthenticator.from_settings(settings)
    try:
        identity = authenticator.authenticate_credentials(username, password)
    except AuthError as error:
        st.error(f"登录失败：{error}")
        return

    st.session_state[_LOCAL_IDENTITY_STATE_KEY] = identity
    st.rerun()


def _render_local_identity_status(identity: IdentityContext) -> None:
    """Show a local account identity and a session-scoped logout action."""

    st.markdown(
        f"""
        <div class="pkb-side-status">
            <strong><span class="pkb-status-dot"></span>当前登录身份</strong>
            <p>{_html(_identity_display_name(identity))} · 角色：{_html(identity.role.display_name)}</p>
            <p>已通过本地账号登录</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("退出登录", key="local_logout", use_container_width=True):
        st.session_state.pop(_LOCAL_IDENTITY_STATE_KEY, None)
        st.rerun()


def _cloudflare_logout_url() -> str:
    """Return the official Cloudflare Access logout path.

    The path is intentionally relative so the browser resolves it against the
    current application origin without embedding an internal server host or
    deployment-specific URL in the page.
    """

    return _CLOUDFLARE_LOGOUT_PATH


def _identity_display_name(identity: IdentityContext) -> str:
    """Return a UI-safe display name without echoing the email claim."""

    name = (identity.display_name or "").strip()
    if not name:
        return "已认证用户"
    if identity.email and name.casefold() == identity.email.casefold():
        return "已认证用户"
    return name


def _render_identity_status(
    identity: IdentityContext,
    *,
    auth_mode: str = "cloudflare",
) -> None:
    """Show safe identity fields without exposing claims or server paths."""

    if auth_mode == "local":
        _render_local_identity_status(identity)
        return

    st.markdown(
        f"""
        <div class="pkb-side-status">
            <strong><span class="pkb-status-dot"></span>当前登录身份</strong>
            <p>{_html(_identity_display_name(identity))} · 角色：{_html(identity.role.display_name)}</p>
            <p>已通过 Cloudflare Access 认证</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.link_button(
        "退出登录 / 重新登录",
        _cloudflare_logout_url(),
        use_container_width=True,
    )


def _render_sidebar(
    service: UIService,
    *,
    identity: IdentityContext | None = None,
    auth_mode: str = "cloudflare",
) -> None:
    with st.sidebar:
        st.markdown(
            """
            <div class="pkb-sidebar-brand">
                <span class="pkb-mark" aria-label="Personal AI Knowledge Base">PKB</span><span class="pkb-brand-name">个人 AI 知识库</span>
                <div class="pkb-sidebar-eyebrow">Your thinking, organized</div>
                <p class="pkb-sidebar-copy">把每次阅读和思考，留成下一次创作可以复用的材料。</p>
            </div>
            <div class="pkb-side-status">
                <strong><span class="pkb-status-dot"></span>Local workspace</strong>
                <p>数据保留在本机，导入后自动生成 Note 与 JSON Index。</p>
            </div>
            <div class="pkb-side-label">Workflow</div>
            <div class="pkb-side-flow"><span>01</span>导入资料与观点</div>
            <div class="pkb-side-flow"><span>02</span>检索问题与证据</div>
            <div class="pkb-side-flow"><span>03</span>综合主题知识</div>
            <div class="pkb-side-flow"><span>04</span>确认选题与口播</div>
            """,
            unsafe_allow_html=True,
        )
        st.divider()
        st.markdown('<div class="pkb-side-label">Storage</div>', unsafe_allow_html=True)
        if identity is None:
            st.caption(f"数据目录：{service.paths.data_dir}")
            st.caption("V1 使用本地文件、可配置 AI Provider 和 JSON Index。")
        else:
            _render_identity_status(identity, auth_mode=auth_mode)
            if auth_mode == "local":
                st.caption("本地账号模式已启用；数据按当前登录身份隔离。")
            else:
                st.caption("V2 认证已启用；数据按当前登录身份隔离。")
        _render_provider_configuration()
        _render_embedding_configuration()


def _service_for_session_values(
    default_service: UIService,
    provider: dict[str, str] | None,
    embedding: dict[str, str] | None,
) -> UIService:
    """Compose independent browser-session bindings over the default service."""

    values = provider
    if values is not None:
        return UIService.with_session_provider(
            default_service.paths,
            provider_name=values["provider_name"],
            model=values["model"],
            base_url=values["base_url"],
            api_key=values["api_key"],
            **(embedding or {}),
        )
    if embedding is not None:
        return UIService.with_session_embedding(
            default_service.paths,
            provider=default_service.provider,
            **embedding,
        )
    return default_service


def _service_for_current_session(default_service: UIService) -> UIService:
    """Overlay browser-only credentials onto the default service binding."""

    return _service_for_session_values(
        default_service,
        _provider_session_values(),
        _embedding_session_values(),
    )


def _render_section_header(
    index: str,
    title: str,
    description: str,
    *,
    accent: str,
) -> None:
    st.markdown(
        f"""
        <div class="pkb-section-head pkb-accent-{_html(accent)}">
            <div class="pkb-section-index">{_html(index)}</div>
            <div>
                <div class="pkb-card-kicker">{_html(index)} / WORKFLOW</div>
                <h2>{_html(title)}</h2>
                <p>{_html(description)}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_card_heading(kicker: str, title: str, description: str) -> None:
    st.markdown(
        f"""
        <div class="pkb-card-heading">
            <div class="pkb-card-kicker">{_html(kicker)}</div>
            <h3>{_html(title)}</h3>
            <p>{_html(description)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_ingest_result(result: IngestResult | None) -> None:
    if result is None:
        return
    document = result.document
    with st.container(border=True):
        st.markdown(
            f"""
            <div class="pkb-result-head">
                <div>
                    <span class="pkb-status-pill pkb-status-success">Saved locally</span>
                    <h3>{_html(document.title or document.id)}</h3>
                </div>
                <div class="pkb-result-count"><small>INDEX</small>{len(result.index.entries)} entries</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        columns = st.columns(3)
        columns[0].metric("Raw ID", document.id[:12])
        columns[1].metric("Note", "已生成" if result.note else "未生成")
        columns[2].metric("Index", f"{len(result.index.entries)} 条")
        st.caption(f"Raw：{document.original_file or '本地记录'}")
        st.caption(f"Note：{result.note.path}")


def _render_wechat_import(service: UIService) -> None:
    """Render the manual WeChat route and its explicit fetch fallback."""

    _render_card_heading(
        "CAPTURE / WECHAT",
        "导入微信公众号文章",
        "仅接受 https://mp.weixin.qq.com/s/...。可以先尝试自动提取，失败后补充标题和正文。",
    )
    with st.form("wechat_import_form"):
        source_url = st.text_input(
            "原始公众号文章 URL",
            placeholder="https://mp.weixin.qq.com/s/...",
        )
        title = st.text_input("文章标题（自动提取失败时必填）")
        content = st.text_area(
            "文章正文（自动提取失败时必填）",
            height=180,
            placeholder="粘贴公众号文章正文",
        )
        submitted = st.form_submit_button(
            "导入公众号文章",
            type="primary",
            use_container_width=True,
        )
    if submitted:
        st.session_state["wechat_import_result"] = None
        try:
            result = service.import_wechat_article(
                source_url,
                title=title,
                content=content,
            )
            st.session_state["wechat_import_result"] = result
            if result.succeeded:
                assert result.document is not None
                assert result.note is not None
                assert result.index is not None
                st.session_state["last_ingest"] = IngestResult(
                    document=result.document,
                    note=result.note,
                    index=result.index,
                )
                _invalidate_results_after_ingest(st.session_state)
                st.session_state["ingest_notice"] = "已导入微信公众号文章。"
                st.session_state["wechat_import_result"] = None
                st.rerun()
            st.warning(result.message)
        except Exception as error:
            _show_error(error)

    result = st.session_state.get("wechat_import_result")
    if result is not None and result.status == "manual_required":
        st.info("自动提取未得到完整文章；请保留 URL，并补充非空标题和正文后再次提交。")


def _render_retrieval(result: Any, *, heading: str = "检索结果") -> None:
    if result is None:
        return
    with st.container(border=True):
        st.markdown(
            f"""
            <div class="pkb-result-head">
                <div>
                    <span class="pkb-status-pill pkb-status-neutral">{_html(result.status)}</span>
                    <h3>{_html(heading)}</h3>
                </div>
                <div class="pkb-result-count"><small>CANDIDATES</small>{len(result.candidates)} 条</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if not result.candidates:
            st.info("没有命中本地 Index。试试更具体的关键词，或先导入一条资料。")
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


def _source_web_url(source: Any) -> str | None:
    """Return a safe HTTP(S) original-source URL when one is available."""

    for value in (getattr(source, "reference", None), getattr(source, "path", None)):
        if not isinstance(value, str):
            continue
        parsed = urlparse(value.strip())
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return value.strip()
    return None


def _source_raw_path(source: Any, raw_dir: Path) -> Path | None:
    """Resolve an immutable local original without trusting arbitrary paths."""

    if getattr(source, "kind", None) not in {"note", "raw"}:
        return None
    source_id = getattr(source, "source_id", "")
    if not isinstance(source_id, str) or not source_id or Path(source_id).name != source_id:
        return None
    directory = raw_dir / source_id
    for filename in ("original.pdf", "original.txt"):
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


def _render_sources(sources: Sequence[Any], *, raw_dir: Path) -> None:
    if not sources:
        st.caption("暂无可展示的来源链。")
        return
    st.markdown('<div class="pkb-source-heading">来源链</div>', unsafe_allow_html=True)
    for index, source in enumerate(sources):
        location = source.path or source.reference or source.source_id
        availability = "可读取" if source.available else "不可读取"
        title = source.title or source.source_id
        with st.container(border=True):
            st.markdown(
                f"<div class=\"pkb-source-row\"><span class=\"pkb-source-kind\">{_html(source.kind)}</span>"
                f"<strong>{_html(title)}</strong><span>{_html(availability)} · {_html(location)}</span></div>",
                unsafe_allow_html=True,
            )
            web_url = _source_web_url(source)
            raw_path = _source_raw_path(source, raw_dir)
            if web_url:
                st.link_button("打开原文网页", web_url, use_container_width=True)
            elif raw_path is not None and raw_path.suffix.lower() == ".pdf":
                st.download_button(
                    "下载原始 PDF",
                    data=raw_path.read_bytes(),
                    file_name=f"{raw_path.parent.name}.pdf",
                    mime="application/pdf",
                    key=f"source-pdf-{index}-{source.source_id}",
                    use_container_width=True,
                )
            elif raw_path is not None:
                with st.expander("查看原始文本"):
                    st.text(raw_path.read_text(encoding="utf-8"))


def _render_import_tab(service: UIService) -> None:
    _render_section_header(
        "01",
        "导入与观点",
        "先把可追溯的原始材料放进来，再用观点卡片补上你自己的判断。每次写入都会同步 Note 与本地 Index。",
        accent="purple",
    )
    _render_wechat_import(service)
    pdf_column, idea_column = st.columns([1, 1], gap="large")
    with pdf_column:
        _render_card_heading("CAPTURE / PDF", "导入文本型 PDF", "适合保存文章、报告或课程材料。")
        with st.form("pdf_import_form", clear_on_submit=True):
            uploaded = st.file_uploader(
                "选择文本型 PDF",
                type=["pdf"],
                accept_multiple_files=True,
            )
            submitted = st.form_submit_button(
                "导入 PDF",
                type="primary",
                use_container_width=True,
            )
        if submitted:
            if not uploaded:
                st.warning("请先选择至少一个 PDF 文件。")
            else:
                imported = 0
                for pdf_file in uploaded:
                    try:
                        st.session_state["last_ingest"] = service.import_pdf(
                            pdf_file.name,
                            pdf_file.getvalue(),
                        )
                        imported += 1
                    except Exception as error:
                        st.error(f"{pdf_file.name}：{error}")
                if imported:
                    _invalidate_results_after_ingest(st.session_state)
                    st.session_state["ingest_notice"] = f"已导入 {imported} 个 PDF 文件。"
                    st.rerun()
    with idea_column:
        _render_card_heading("CAPTURE / IDEA", "添加观点卡片", "把好句、灵感和自己的备注及时留下。")
        with st.form("idea_form", clear_on_submit=True):
            idea_content = st.text_area("观点 / 好句 / 灵感", height=130)
            idea_source = st.text_input("来源 URL（可选）")
            idea_tags = st.text_input("标签（可选，用逗号分隔）")
            idea_note = st.text_area("个人备注（可选）", height=90)
            submitted = st.form_submit_button(
                "保存观点卡片",
                type="primary",
                use_container_width=True,
            )
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
    if st.session_state["last_ingest"] is not None:
        if notice := st.session_state.pop("ingest_notice", None):
            st.success(notice)
        st.markdown(
            '<div class="pkb-card-kicker" style="margin:1.6rem 0 0.65rem;">Latest activity</div>',
            unsafe_allow_html=True,
        )
        _render_ingest_result(st.session_state["last_ingest"])


def _render_search_qa_tab(service: UIService) -> None:
    _render_section_header(
        "02",
        "Search / Q&A",
        "用关键词快速定位，或直接提出问题。答案和候选都会保留来源链，方便回到原始材料复核。",
        accent="blue",
    )
    search_column, qa_column = st.columns([0.9, 1.1], gap="large")
    with search_column:
        _render_card_heading("EXPLORE / SEARCH", "检索本地知识", "从已生成的 Note 与 Index 中找相关材料。")
        with st.form("search_form"):
            query = st.text_input("检索词", placeholder="例如：AI 工作流")
            limit = st.number_input("最多返回", min_value=1, max_value=50, value=10, step=1)
            submitted = st.form_submit_button(
                "开始检索",
                type="primary",
                use_container_width=True,
            )
        if submitted:
            try:
                st.session_state["search_result"] = service.search(
                    query,
                    limit=int(limit),
                )
            except EmbeddingRequestError:
                st.warning("语义检索服务暂时不可用，已切换为本地关键词检索。")
                st.session_state["search_result"] = service.search(
                    query,
                    limit=int(limit),
                    include_embeddings=False,
                )
            except Exception as error:
                _show_error(error)
    with qa_column:
        _render_card_heading("EXPLORE / Q&A", "向你的知识库提问", "回答只使用本地 Knowledge、Notes 和 Raw 来源。")
        with st.form("qa_form"):
            question = st.text_area(
                "问题",
                height=100,
                placeholder="例如：我关于 AI 工作流的共同判断是什么？",
            )
            qa_limit = st.number_input(
                "最多使用的候选",
                min_value=1,
                max_value=50,
                value=10,
                step=1,
                key="qa_limit",
            )
            submitted = st.form_submit_button(
                "生成回答",
                type="primary",
                use_container_width=True,
            )
        if submitted:
            try:
                st.session_state["qa_result"] = service.answer(
                    question,
                    limit=int(qa_limit),
                )
            except EmbeddingRequestError:
                st.warning("语义检索服务暂时不可用，已使用本地关键词检索生成回答。")
                st.session_state["qa_result"] = service.answer(
                    question,
                    limit=int(qa_limit),
                    include_embeddings=False,
                )
            except Exception as error:
                _show_error(error)
    _render_retrieval(st.session_state["search_result"], heading="检索结果")
    result = st.session_state["qa_result"]
    if result is not None:
        status_class = (
            "pkb-status-success"
            if result.status == "answered"
            else "pkb-status-pending"
        )
        with st.container(border=True):
            st.markdown(
                f"""
                <div class="pkb-result-head">
                    <div>
                        <span class="pkb-status-pill {status_class}">{_html(result.status)}</span>
                        <h3>回答</h3>
                    </div>
                    <div class="pkb-result-count"><small>EVIDENCE</small>{_html(result.evidence_level)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if result.answer:
                st.markdown(result.answer)
            else:
                st.info(result.reason)
            _render_sources(result.sources, raw_dir=service.paths.raw_dir)
            for evidence in result.evidence:
                st.caption(f"{evidence.source_kind}：{evidence.explanation}")


def _render_synthesis_tab(service: UIService) -> None:
    _render_section_header(
        "03",
        "Topic synthesis",
        "输入一个主题，让 Knowledge Compiler 把当前本地 Notes 汇总成可以反复回看的主题页。",
        accent="yellow",
    )
    _render_card_heading("DISTILL / KNOWLEDGE", "生成主题综合", "主题页会记录参与综合的来源，便于继续追踪。")
    with st.form("synthesis_form"):
        topic = st.text_input("主题", placeholder="例如：AI 工作流")
        submitted = st.form_submit_button(
            "生成主题综合",
            type="primary",
            use_container_width=True,
        )
    if submitted:
        try:
            st.session_state["knowledge_result"] = service.synthesize_topic(topic)
        except Exception as error:
            _show_error(error)
    result = st.session_state["knowledge_result"]
    if result is not None:
        with st.container(border=True):
            st.markdown(
                f"""
                <div class="pkb-result-head">
                    <div>
                        <span class="pkb-status-pill pkb-status-success">Saved knowledge</span>
                        <h3>{_html(result.knowledge.topic)}</h3>
                    </div>
                    <div class="pkb-result-count"><small>SOURCES</small>{len(result.knowledge.sources)} 条</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            synthesis = result.knowledge.current_synthesis
            if synthesis:
                st.markdown('<div class="pkb-card-kicker">CURRENT SYNTHESIS</div>', unsafe_allow_html=True)
                st.markdown(synthesis)
            else:
                st.info("当前主题还没有生成综合内容。")
            st.caption(f"Knowledge：{result.path}")
            st.markdown('<div class="pkb-source-heading">来源链</div>', unsafe_allow_html=True)
            for source in result.knowledge.sources:
                st.caption(
                    f"note · {source.title or source.note_id} · "
                    f"{source.reference or source.note_id}",
                )


def _render_candidate(candidate: Any, rank: int) -> None:
    with st.expander(f"{rank}. {candidate.title} · {candidate.score:.3f}"):
        st.markdown(
            f'<div class="pkb-card-kicker">CANDIDATE {rank:02d}</div>',
            unsafe_allow_html=True,
        )
        st.write(candidate.why_worth_doing)
        for reason in candidate.reasons:
            st.caption(f"{reason.rule}：{reason.explanation}")
        for evidence in candidate.evidence:
            st.caption(f"{evidence.signal}：{', '.join(evidence.values)}")
        for source in candidate.sources:
            st.caption(f"来源 {source.kind}：{source.title or source.source_id} · {source.path}")


def _topic_gate_state(
    candidates: Sequence[Any],
    selected_title: str | None,
    confirmed: bool,
) -> tuple[str, str, bool]:
    """Return presentation state for the explicit topic-to-script gate."""

    candidate = find_candidate(candidates, selected_title)
    if candidate is None:
        return "待选择", "先选择一个候选选题，再进行确认。", False
    if not confirmed:
        return "待确认", f"已选择「{selected_title}」，点击确认后才可以生成口播。", False
    allowed = can_generate_script(candidates, selected_title, confirmed)
    return "已确认", f"「{selected_title}」已确认，可以生成口播。", allowed


def _render_topics_tab(service: UIService) -> None:
    _render_section_header(
        "04",
        "选题与口播",
        "候选来自本地 Index、Notes 和 Topic Knowledge。确认一个方向之后，才会开放口播生成。",
        accent="pink",
    )
    _render_card_heading("PUBLISH / TOPICS", "生成可解释的选题", "先看依据，再决定哪一个方向值得继续。")
    if st.button(
        "生成选题",
        type="primary",
        use_container_width=True,
        key="generate_topics_button",
    ):
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
    with st.container(border=True):
        st.markdown(
            f"""
            <div class="pkb-result-head">
                <div>
                    <span class="pkb-status-pill pkb-status-neutral">Topic radar</span>
                    <h3>候选选题</h3>
                </div>
                <div class="pkb-result-count"><small>SHORTLIST</small>{len(topics_result.candidates)} 条</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.info(topics_result.message)
        for rank, candidate in enumerate(topics_result.candidates, start=1):
            _render_candidate(candidate, rank)
    if not topics_result.candidates:
        return

    st.markdown(
        """
        <div class="pkb-gate-card">
            <div class="pkb-card-kicker">DECISION GATE</div>
            <h3>确认一个方向，解锁口播</h3>
            <p>选择只是浏览状态；只有明确点击确认，生成口播按钮才会开放。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
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
        use_container_width=True,
    ):
        st.session_state["topic_selection_confirmed"] = True
        st.session_state["script_result"] = None
        st.success(f"已确认：{selected_title}")

    gate_label, gate_message, allowed = _topic_gate_state(
        topics_result.candidates,
        selected_title,
        st.session_state["topic_selection_confirmed"],
    )
    gate_tone = "confirmed" if allowed else "pending"
    st.markdown(
        f'<span class="pkb-status-pill pkb-status-{gate_tone}">{_html(gate_label)}</span>',
        unsafe_allow_html=True,
    )
    st.caption(gate_message)
    if st.button(
        "生成口播",
        disabled=not allowed,
        key="generate_script_button",
        use_container_width=True,
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
    with st.container(border=True):
        st.markdown(
            f"""
            <div class="pkb-result-head">
                <div>
                    <span class="pkb-status-pill pkb-status-success">{_html(script_result.status)}</span>
                    <h3>口播结果</h3>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if script_result.script:
            st.success(script_result.message)
            script_title = getattr(script_result, "title", None)
            if script_title:
                st.text_input("建议发布标题", value=script_title)
            st.text_area("口播稿", value=script_result.script_text, height=360)
        else:
            st.warning(script_result.message)
        _render_retrieval(script_result.retrieval, heading="二次检索")
        _render_sources(script_result.sources, raw_dir=service.paths.raw_dir)
        for evidence in script_result.evidence:
            st.caption(f"{evidence.source_kind}：{evidence.explanation}")


def main(service: UIService | None = None) -> None:
    """Render the responsive single-page application."""

    st.set_page_config(
        page_title="Personal AI Knowledge Base",
        page_icon="✦",
        layout="wide",
        initial_sidebar_state="auto",
    )
    _install_translation_guard()
    _init_state()
    _render_theme()
    settings = get_settings()
    if settings.auth_enabled and settings.auth_mode == "local":
        identity = _local_identity_from_session()
        if identity is None:
            _render_local_login(settings)
            st.stop()
    else:
        try:
            identity = _identity_for_settings(settings)
        except AuthError as error:
            st.error(f"V2 认证失败：{error}")
            st.stop()

    default_service = service or UIService(identity=identity)

    _render_sidebar(
        default_service,
        identity=identity,
        auth_mode=settings.auth_mode,
    )
    active_service = default_service if service is not None else _service_for_current_session(default_service)
    _render_brand_header()
    _render_flow_overview()

    import_tab, search_tab, synthesis_tab, topics_tab = st.tabs(
        ["01 导入与观点", "02 Search / Q&A", "03 Topic synthesis", "04 选题与口播"],
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
