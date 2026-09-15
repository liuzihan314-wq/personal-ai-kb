"""Manual import adapter for public WeChat official-account articles.

The adapter deliberately keeps the supported URL surface narrow.  A public
article URL may be fetched as a convenience, but a failed fetch always falls
back to an explicit manual title/body submission and never creates a partial
Raw record.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import ssl
from typing import Literal
from urllib.parse import urlsplit, urlunsplit
import urllib.request

import certifi

from pkb.config import get_settings
from pkb.index import IndexBuilder, IndexFile
from pkb.models import UnifiedDocument
from pkb.notes import NoteGenerationResult, NoteService
from pkb.providers import AIProvider, MockAIProvider
from pkb.storage import RawStorage


WECHAT_ARTICLE_CONTENT_TYPE = "article"
WECHAT_SOURCE_TYPE = "wechat"
WECHAT_INGEST_MODE = "manual"
MANUAL_REQUIRED_STATUS = "manual_required"
MANUAL_REQUIRED_MESSAGE = "自动提取失败，请补充非空标题和正文后重新提交。"
WECHAT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "MicroMessenger/8.0.50(0x18003237) NetType/WIFI Language/zh_CN"
)


class WeChatImportError(ValueError):
    """Base error for the supported manual WeChat article route."""


class InvalidWeChatURL(WeChatImportError):
    """Raised when a URL is outside the official-account article allow-list."""


WeChatURLValidationError = InvalidWeChatURL


class WeChatManualImportError(WeChatImportError):
    """Raised when a manual article field is empty or invalid."""


class ManualImportRequired(WeChatImportError):
    """Raised internally when URL fetching cannot produce a complete article."""

    code = MANUAL_REQUIRED_STATUS


ManualRequiredError = ManualImportRequired


@dataclass(frozen=True)
class FetchedWeChatArticle:
    """The small set of fields extracted from a public article page."""

    title: str
    content: str
    source_url: str
    author: str | None = None
    published_at: datetime | None = None


@dataclass(frozen=True)
class WeChatImportResult:
    """The outcome shared by CLI and UI callers of the Core Service."""

    status: Literal["imported", "existing", "manual_required"]
    message: str
    document: UnifiedDocument | None = None
    note: NoteGenerationResult | None = None
    index: IndexFile | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether a complete Raw → Note → Index result exists."""

        return (
            self.status in {"imported", "existing"}
            and self.document is not None
            and self.note is not None
            and self.index is not None
        )


def normalize_wechat_article_url(source_url: str) -> str:
    """Validate and canonicalize one supported public article URL.

    Tracking query parameters and fragments are intentionally removed from the
    identity.  The article path is the stable identity used for idempotence.
    """

    if not isinstance(source_url, str) or not source_url.strip():
        raise InvalidWeChatURL("原始公众号 URL 不能为空")

    value = source_url.strip()
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise InvalidWeChatURL("公众号 URL 格式不受支持")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise InvalidWeChatURL("公众号 URL 格式不受支持") from exc

    if parsed.scheme.casefold() != "https":
        raise InvalidWeChatURL("仅支持 https://mp.weixin.qq.com/s/... 公众号文章 URL")
    if hostname is None or hostname.casefold() != "mp.weixin.qq.com":
        raise InvalidWeChatURL("仅支持 https://mp.weixin.qq.com/s/... 公众号文章 URL")
    if parsed.username or parsed.password or port is not None:
        raise InvalidWeChatURL("公众号 URL 格式不受支持")

    path = parsed.path
    if not path.startswith("/s/"):
        raise InvalidWeChatURL("仅支持 https://mp.weixin.qq.com/s/... 公众号文章 URL")
    article_key = path[3:].strip("/")
    if not article_key or "/" in article_key:
        raise InvalidWeChatURL("仅支持 https://mp.weixin.qq.com/s/... 公众号文章 URL")

    return urlunsplit(("https", "mp.weixin.qq.com", f"/s/{article_key}", "", ""))


def is_wechat_article_url(source_url: str) -> bool:
    """Return whether ``source_url`` passes the strict article allow-list."""

    try:
        normalize_wechat_article_url(source_url)
    except InvalidWeChatURL:
        return False
    return True


def _document_id(normalized_url: str) -> str:
    return sha256(f"wechat-article\0{normalized_url}".encode("utf-8")).hexdigest()


def _clean_text(value: str) -> str:
    """Collapse HTML whitespace while retaining paragraph boundaries."""

    lines = [" ".join(line.replace("\xa0", " ").split()) for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = _clean_text(value)
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(normalized)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class _ArticleHTMLParser(HTMLParser):
    """Extract text from the stable public article containers without a DOM dependency."""

    _BLOCK_TAGS = {
        "article",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "li",
        "p",
        "section",
        "tr",
    }
    _SKIP_TAGS = {"script", "style", "noscript"}
    _VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta_title: str | None = None
        self.document_title_parts: list[str] = []
        self.content_parts: list[str] = []
        self.author_parts: list[str] = []
        self.publish_time_parts: list[str] = []
        self._title_depth = 0
        self._document_title_depth = 0
        self._content_depth = 0
        self._author_depth = 0
        self._publish_time_depth = 0
        self._skip_depth = 0

    @staticmethod
    def _attributes(attributes: list[tuple[str, str | None]]) -> dict[str, str]:
        return {
            key.casefold(): value or ""
            for key, value in attributes
            if key
        }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        attributes = self._attributes(attrs)
        element_id = attributes.get("id", "").casefold()
        classes = set(attributes.get("class", "").casefold().split())

        if tag == "meta":
            property_name = (
                attributes.get("property", "")
                or attributes.get("name", "")
            ).casefold()
            if property_name in {"og:title", "twitter:title"} and not self.meta_title:
                self.meta_title = attributes.get("content", "")

        if self._title_depth:
            self._title_depth += 1
        elif element_id == "activity-name":
            self._title_depth = 1

        if self._document_title_depth:
            self._document_title_depth += 1
        elif tag == "title":
            self._document_title_depth = 1

        is_content_root = (
            element_id == "js_content"
            or "rich_media_content" in classes
        )
        if self._content_depth:
            if tag in self._BLOCK_TAGS:
                self.content_parts.append("\n")
            if tag not in self._VOID_TAGS:
                self._content_depth += 1
        elif is_content_root:
            self._content_depth = 1

        if self._author_depth:
            self._author_depth += 1
        elif element_id in {"js_name", "profile_nickname"}:
            self._author_depth = 1

        if self._publish_time_depth:
            self._publish_time_depth += 1
        elif element_id in {"publish_time", "js_publish_time"}:
            self._publish_time_depth = 1

        if self._content_depth and tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() in self._VOID_TAGS:
            if self._content_depth and tag.casefold() in self._BLOCK_TAGS:
                self.content_parts.append("\n")
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in self._VOID_TAGS:
            return
        if self._content_depth and tag in self._BLOCK_TAGS:
            self.content_parts.append("\n")
        if self._content_depth and tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if self._content_depth:
            self._content_depth -= 1
        if self._title_depth:
            self._title_depth -= 1
        if self._document_title_depth:
            self._document_title_depth -= 1
        if self._author_depth:
            self._author_depth -= 1
        if self._publish_time_depth:
            self._publish_time_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._title_depth:
            self.title_parts.append(data)
        if self._document_title_depth:
            self.document_title_parts.append(data)
        if self._content_depth and not self._skip_depth:
            self.content_parts.append(data)
        if self._author_depth:
            self.author_parts.append(data)
        if self._publish_time_depth:
            self.publish_time_parts.append(data)

    def article(self, source_url: str) -> FetchedWeChatArticle:
        title = (
            _clean_text("".join(self.title_parts))
            or _clean_text(self.meta_title or "")
            or _clean_text("".join(self.document_title_parts))
        )
        content = _clean_text("".join(self.content_parts))
        if not title or not content:
            raise ManualImportRequired(MANUAL_REQUIRED_MESSAGE)
        author = _clean_text("".join(self.author_parts)) or None
        published_at = _parse_datetime("".join(self.publish_time_parts))
        return FetchedWeChatArticle(
            title=title,
            content=content,
            source_url=source_url,
            author=author,
            published_at=published_at,
        )


def _parse_article_html(html: bytes | str, source_url: str) -> FetchedWeChatArticle:
    if isinstance(html, bytes):
        decoded = html.decode("utf-8-sig", errors="replace")
    elif isinstance(html, str):
        decoded = html
    else:
        raise ManualImportRequired(MANUAL_REQUIRED_MESSAGE)
    if not decoded.strip():
        raise ManualImportRequired(MANUAL_REQUIRED_MESSAGE)
    parser = _ArticleHTMLParser()
    try:
        parser.feed(decoded)
        parser.close()
    except (ValueError, AssertionError) as exc:
        raise ManualImportRequired(MANUAL_REQUIRED_MESSAGE) from exc
    return parser.article(source_url)


class _AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects outside the same canonical public article URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        normalize_wechat_article_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


ArticleFetcher = Callable[[str], bytes | str]


class WeChatArticleImporter:
    """Build immutable article Raw records and optionally fetch public HTML."""

    def __init__(
        self,
        raw_storage: RawStorage | None = None,
        *,
        raw_dir: str | Path | None = None,
        clock: Callable[[], datetime] | None = None,
        fetcher: ArticleFetcher | None = None,
        timeout: float = 15.0,
    ) -> None:
        if raw_storage is not None and raw_dir is not None:
            raise ValueError("Pass raw_storage or raw_dir, not both")
        self.raw_storage = raw_storage or RawStorage(
            raw_dir if raw_dir is not None else get_settings().raw_dir
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.fetcher = fetcher
        self.timeout = timeout

    def fetch_article(self, source_url: str) -> FetchedWeChatArticle:
        """Fetch and parse one allow-listed public article without writing Raw."""

        normalized_url = normalize_wechat_article_url(source_url)
        try:
            html = self.fetcher(normalized_url) if self.fetcher else self._download(normalized_url)
            return _parse_article_html(html, normalized_url)
        except ManualImportRequired:
            raise
        except Exception as exc:
            raise ManualImportRequired(MANUAL_REQUIRED_MESSAGE) from exc

    def _download(self, normalized_url: str) -> bytes:
        request = urllib.request.Request(
            normalized_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "User-Agent": WECHAT_BROWSER_USER_AGENT,
            },
            method="GET",
        )
        context = ssl.create_default_context(cafile=certifi.where())
        opener = urllib.request.build_opener(
            _AllowlistedRedirectHandler(),
            urllib.request.HTTPSHandler(context=context),
        )
        with opener.open(request, timeout=self.timeout) as response:
            final_url = response.geturl()
            if normalize_wechat_article_url(final_url) != normalized_url:
                raise ManualImportRequired(MANUAL_REQUIRED_MESSAGE)
            return response.read()

    def create(
        self,
        title: str,
        content: str,
        source_url: str,
        *,
        author: str | None = None,
        published_at: datetime | None = None,
    ) -> UnifiedDocument:
        """Create one manual article document or return the existing duplicate."""

        if not isinstance(title, str) or not title.strip():
            raise WeChatManualImportError("文章标题不能为空")
        if not isinstance(content, str) or not content.strip():
            raise WeChatManualImportError("文章正文不能为空")
        normalized_url = normalize_wechat_article_url(source_url)
        source_url_value = source_url.strip()
        document_id = _document_id(normalized_url)
        if self.raw_storage.has_document(document_id):
            return self.raw_storage.load_document(document_id)

        raw_paths = self.raw_storage.paths_for(
            document_id,
            content_type=WECHAT_ARTICLE_CONTENT_TYPE,
        )
        content_bytes = content.encode("utf-8")
        metadata = {
            "ingest_mode": WECHAT_INGEST_MODE,
            "normalized_url": normalized_url,
            "url_sha256": sha256(normalized_url.encode("utf-8")).hexdigest(),
            "content_sha256": sha256(content_bytes).hexdigest(),
            "file_size": len(content_bytes),
            "extracted_text_file": str(raw_paths.extracted_text_file),
            "metadata_file": str(raw_paths.metadata_file),
        }
        document = UnifiedDocument(
            id=document_id,
            content_type=WECHAT_ARTICLE_CONTENT_TYPE,
            title=title.strip(),
            content=content,
            source_type=WECHAT_SOURCE_TYPE,
            source_url=source_url_value,
            author=author.strip() if isinstance(author, str) and author.strip() else None,
            published_at=published_at,
            ingested_at=self.clock(),
            original_file=str(raw_paths.original_file),
            metadata=metadata,
        )
        return self.raw_storage.store(document, content_bytes)

    import_manual = create
    import_article = create


class WeChatArticleService:
    """Shared Core Service for CLI and UI article imports."""

    def __init__(
        self,
        raw_storage: RawStorage | None = None,
        *,
        raw_dir: str | Path | None = None,
        notes_dir: str | Path | None = None,
        index_path: str | Path | None = None,
        provider: AIProvider | None = None,
        clock: Callable[[], datetime] | None = None,
        fetcher: ArticleFetcher | None = None,
        timeout: float = 15.0,
    ) -> None:
        if raw_storage is not None and raw_dir is not None:
            raise ValueError("Pass raw_storage or raw_dir, not both")
        if raw_storage is not None:
            resolved_raw_dir = raw_storage.raw_dir
        else:
            resolved_raw_dir = Path(
                raw_dir if raw_dir is not None else get_settings().raw_dir
            )
        data_dir = resolved_raw_dir.parent
        self.raw_storage = raw_storage or RawStorage(resolved_raw_dir)
        self.notes_dir = Path(notes_dir) if notes_dir is not None else data_dir / "notes"
        self.index_path = (
            Path(index_path)
            if index_path is not None
            else data_dir / "index" / "index.json"
        )
        self.provider = provider if provider is not None else MockAIProvider()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.importer = WeChatArticleImporter(
            self.raw_storage,
            clock=self.clock,
            fetcher=fetcher,
            timeout=timeout,
        )

    def _persist(
        self,
        document: UnifiedDocument,
        *,
        status: Literal["imported", "existing"],
    ) -> WeChatImportResult:
        note = NoteService(
            provider=self.provider,
            notes_dir=self.notes_dir,
            clock=self.clock,
        ).generate(document)
        index = IndexBuilder(
            notes_dir=self.notes_dir,
            index_path=self.index_path,
            clock=self.clock,
        ).rebuild()
        return WeChatImportResult(
            status=status,
            message="公众号文章已导入并更新 Note / Index。"
            if status == "imported"
            else "公众号文章已存在，已复用原有 Raw。",
            document=document,
            note=note,
            index=index,
        )

    def import_manual(
        self,
        title: str,
        content: str,
        source_url: str,
    ) -> WeChatImportResult:
        """Persist a title/body/source triple without any network request."""

        normalized_url = normalize_wechat_article_url(source_url)
        document_id = _document_id(normalized_url)
        existed = self.raw_storage.has_document(document_id)
        document = self.importer.create(title, content, source_url)
        return self._persist(document, status="existing" if existed else "imported")

    def import_article(
        self,
        source_url: str,
        *,
        title: str | None = None,
        content: str | None = None,
    ) -> WeChatImportResult:
        """Import manually when complete fields exist, otherwise try safe fetch."""

        normalized_url = normalize_wechat_article_url(source_url)
        document_id = _document_id(normalized_url)
        if self.raw_storage.has_document(document_id):
            document = self.raw_storage.load_document(document_id)
            return self._persist(document, status="existing")

        has_manual_title = isinstance(title, str) and bool(title.strip())
        has_manual_content = isinstance(content, str) and bool(content.strip())
        if has_manual_title and has_manual_content:
            document = self.importer.create(title, content, source_url)
            return self._persist(document, status="imported")

        try:
            fetched = self.importer.fetch_article(normalized_url)
        except ManualImportRequired:
            return WeChatImportResult(
                status=MANUAL_REQUIRED_STATUS,
                message=MANUAL_REQUIRED_MESSAGE,
            )

        effective_title = title.strip() if has_manual_title else fetched.title
        effective_content = content if has_manual_content else fetched.content
        try:
            document = self.importer.create(
                effective_title,
                effective_content,
                source_url,
                author=fetched.author,
                published_at=fetched.published_at,
            )
        except WeChatManualImportError:
            return WeChatImportResult(
                status=MANUAL_REQUIRED_STATUS,
                message=MANUAL_REQUIRED_MESSAGE,
            )
        return self._persist(document, status="imported")


def import_wechat_article(
    source_url: str,
    *,
    title: str | None = None,
    content: str | None = None,
    raw_dir: str | Path | None = None,
    notes_dir: str | Path | None = None,
    index_path: str | Path | None = None,
    provider: AIProvider | None = None,
    fetcher: ArticleFetcher | None = None,
) -> WeChatImportResult:
    """Convenience wrapper around the shared article Core Service."""

    return WeChatArticleService(
        raw_dir=raw_dir,
        notes_dir=notes_dir,
        index_path=index_path,
        provider=provider,
        fetcher=fetcher,
    ).import_article(source_url, title=title, content=content)


def import_manual_wechat_article(
    title: str,
    content: str,
    source_url: str,
    *,
    raw_dir: str | Path | None = None,
    notes_dir: str | Path | None = None,
    index_path: str | Path | None = None,
    provider: AIProvider | None = None,
) -> WeChatImportResult:
    """Convenience wrapper for the no-network manual article route."""

    return WeChatArticleService(
        raw_dir=raw_dir,
        notes_dir=notes_dir,
        index_path=index_path,
        provider=provider,
    ).import_manual(title, content, source_url)


__all__ = [
    "ArticleFetcher",
    "FetchedWeChatArticle",
    "InvalidWeChatURL",
    "MANUAL_REQUIRED_MESSAGE",
    "MANUAL_REQUIRED_STATUS",
    "ManualImportRequired",
    "ManualRequiredError",
    "WECHAT_ARTICLE_CONTENT_TYPE",
    "WECHAT_INGEST_MODE",
    "WECHAT_SOURCE_TYPE",
    "WeChatArticleImporter",
    "WeChatArticleService",
    "WeChatImportError",
    "WeChatImportResult",
    "WeChatManualImportError",
    "WeChatURLValidationError",
    "import_manual_wechat_article",
    "import_wechat_article",
    "is_wechat_article_url",
    "normalize_wechat_article_url",
]
