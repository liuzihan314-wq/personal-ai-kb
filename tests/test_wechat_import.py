import json
from pathlib import Path
import ssl
import urllib.request

import pytest
from typer.testing import CliRunner

from pkb.cli.main import app
from pkb.ingest.wechat import (
    MANUAL_REQUIRED_STATUS,
    ManualImportRequired,
    WeChatArticleImporter,
    WeChatArticleService,
    WeChatManualImportError,
    WECHAT_BROWSER_USER_AGENT,
    InvalidWeChatURL,
    is_wechat_article_url,
    normalize_wechat_article_url,
)
from pkb.models import UnifiedDocument
from pkb.providers import MockAIProvider
from pkb.storage import RawStorage
from pkb.ui import UIPaths, UIService


runner = CliRunner()
ARTICLE_URL = "https://mp.weixin.qq.com/s/synthetic-article"
TRACKED_ARTICLE_URL = f"{ARTICLE_URL}?scene=synthetic#section"


def _synthetic_article_html() -> bytes:
    return """
    <html>
      <head>
        <meta property="og:title" content="Synthetic WeChat Article" />
      </head>
      <body>
        <h1 id="activity-name">Synthetic WeChat Article</h1>
        <span id="js_name">Synthetic Author</span>
        <div id="js_content">
          <p>第一段合成正文，验证公众号文章导入。</p>
          <p>第二段保留换行，并跳过<img src="fixture.png" />
            <script>private fixture marker</script>脚本。</p>
        </div>
        <div id="fixture-footer">正文之后的页脚不应进入 Raw。</div>
      </body>
    </html>
    """.encode("utf-8")


def test_wechat_url_allow_list_is_strict_and_normalizes_tracking_parts():
    assert normalize_wechat_article_url(TRACKED_ARTICLE_URL) == ARTICLE_URL
    assert is_wechat_article_url(ARTICLE_URL)

    invalid_urls = (
        "http://mp.weixin.qq.com/s/synthetic-article",
        "https://www.example.test/s/synthetic-article",
        "https://channels.weixin.qq.com/s/synthetic-article",
        "https://weixin.qq.com/s/synthetic-article",
        "https://mp.weixin.qq.com/cgi-bin/synthetic-article",
        "https://mp.weixin.qq.com/s/",
        "https://mp.weixin.qq.com/s/synthetic-article/extra",
        "https://user:pass@mp.weixin.qq.com/s/synthetic-article",
    )
    for source_url in invalid_urls:
        assert not is_wechat_article_url(source_url)


def test_manual_import_persists_text_raw_note_and_index(tmp_path):
    raw_dir = tmp_path / "data" / "raw"
    notes_dir = tmp_path / "data" / "notes"
    index_path = tmp_path / "data" / "index" / "index.json"
    body = "合成正文第一段。\n\n合成正文第二段。"

    result = WeChatArticleService(
        raw_dir=raw_dir,
        notes_dir=notes_dir,
        index_path=index_path,
        provider=MockAIProvider(),
    ).import_manual("Synthetic title", body, TRACKED_ARTICLE_URL)

    assert result.status == "imported"
    assert result.succeeded
    assert result.document is not None
    assert result.note is not None
    assert result.index is not None
    document = result.document
    assert document == UnifiedDocument.model_validate(document.model_dump())
    assert document.content_type == "article"
    assert document.source_type == "wechat"
    assert document.source_url == TRACKED_ARTICLE_URL
    assert document.metadata["ingest_mode"] == "manual"
    assert Path(document.original_file).name == "original.txt"
    assert Path(document.original_file).read_text(encoding="utf-8") == body
    assert result.note.path.is_file()
    assert result.index.entries[0].document_id == document.id
    assert result.index.entries[0].content_type == "article"

    restarted = RawStorage(raw_dir).load_document(document.id)
    assert restarted == document
    assert json.loads(
        RawStorage(raw_dir).paths_for(document.id).metadata_file.read_text(encoding="utf-8")
    )["metadata"]["ingest_mode"] == "manual"


def test_same_normalized_url_is_idempotent_and_does_not_overwrite_raw(tmp_path):
    raw_dir = tmp_path / "raw"
    importer = WeChatArticleService(
        raw_dir=raw_dir,
        notes_dir=tmp_path / "notes",
        index_path=tmp_path / "index" / "index.json",
        provider=MockAIProvider(),
    )

    first = importer.import_manual("First title", "Original body", TRACKED_ARTICLE_URL)
    assert first.document is not None
    raw_path = Path(first.document.original_file)
    metadata_path = Path(first.document.metadata["metadata_file"])
    original_raw = raw_path.read_bytes()
    original_metadata = metadata_path.read_bytes()

    second = importer.import_manual("Changed title", "Changed body", ARTICLE_URL)

    assert second.status == "existing"
    assert second.document == first.document
    assert raw_path.read_bytes() == original_raw
    assert metadata_path.read_bytes() == original_metadata
    assert sorted(raw_dir.glob("*/original.txt")) == [raw_path]


def test_auto_extract_success_uses_existing_document_contract_without_html_raw(tmp_path):
    service = WeChatArticleService(
        raw_dir=tmp_path / "raw",
        notes_dir=tmp_path / "notes",
        index_path=tmp_path / "index" / "index.json",
        provider=MockAIProvider(),
        fetcher=lambda _url: _synthetic_article_html(),
    )

    result = service.import_article(ARTICLE_URL)

    assert result.status == "imported"
    assert result.document is not None
    assert result.document.title == "Synthetic WeChat Article"
    assert "第一段合成正文" in result.document.content
    assert "private fixture marker" not in result.document.content
    assert "正文之后的页脚" not in result.document.content
    assert result.document.content_type == "article"
    assert result.document.source_type == "wechat"
    assert Path(result.document.original_file).suffix == ".txt"


def test_downloader_uses_certifi_tls_context(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return ARTICLE_URL

        def read(self):
            return b"<html></html>"

    class Opener:
        def open(self, request, *, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

    def build_opener(*handlers):
        captured["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    importer = WeChatArticleImporter(raw_dir=tmp_path / "raw")
    assert importer._download(ARTICLE_URL) == b"<html></html>"
    https_handler = next(
        handler
        for handler in captured["handlers"]
        if isinstance(handler, urllib.request.HTTPSHandler)
    )
    assert isinstance(https_handler._context, ssl.SSLContext)
    assert https_handler._context.verify_mode == ssl.CERT_REQUIRED
    assert https_handler._context.check_hostname
    assert captured["request"].headers["User-agent"] == WECHAT_BROWSER_USER_AGENT
    assert captured["request"].headers["Accept-language"] == "zh-CN,zh;q=0.9"


def test_auto_extract_failure_returns_manual_required_without_raw(tmp_path):
    raw_dir = tmp_path / "raw"
    service = WeChatArticleService(
        raw_dir=raw_dir,
        notes_dir=tmp_path / "notes",
        index_path=tmp_path / "index" / "index.json",
        fetcher=lambda _url: b"<html><body>not an article</body></html>",
    )

    result = service.import_article(ARTICLE_URL)

    assert result.status == MANUAL_REQUIRED_STATUS
    assert result.document is None
    assert "标题" in result.message
    assert not raw_dir.exists()


def test_fetch_failure_is_explicit_and_never_writes_raw(tmp_path):
    raw_dir = tmp_path / "raw"

    def fail(_url):
        raise OSError("synthetic network failure")

    importer = WeChatArticleImporter(raw_dir=raw_dir, fetcher=fail)
    with pytest.raises(ManualImportRequired, match="自动提取失败"):
        importer.fetch_article(ARTICLE_URL)
    assert not raw_dir.exists()


def test_manual_fields_and_invalid_urls_are_rejected_without_raw(tmp_path):
    raw_dir = tmp_path / "raw"
    service = WeChatArticleService(raw_dir=raw_dir, provider=MockAIProvider())

    with pytest.raises(WeChatManualImportError, match="标题不能为空"):
        service.import_manual(" ", "body", ARTICLE_URL)
    with pytest.raises(WeChatManualImportError, match="正文不能为空"):
        service.import_manual("title", "\n", ARTICLE_URL)
    with pytest.raises(InvalidWeChatURL):
        service.import_manual("title", "body", "https://example.test/article")
    assert not raw_dir.exists()


def test_ui_service_uses_shared_wechat_core_service_for_persisted_import(tmp_path):
    paths = UIPaths.from_data_dir(tmp_path)
    result = UIService(paths, provider=MockAIProvider()).import_wechat_article(
        ARTICLE_URL,
        title="UI synthetic title",
        content="UI synthetic body",
    )

    assert result.status == "imported"
    assert result.document is not None
    assert result.note is not None
    assert result.index is not None
    assert result.index.entries[0].document_id == result.document.id


def test_cli_manual_import_uses_configured_data_paths_and_updates_index(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PKB_DATA_DIR", str(data_dir))

    result = runner.invoke(
        app,
        [
            "import-wechat-article",
            TRACKED_ARTICLE_URL,
            "--title",
            "CLI synthetic title",
            "--content",
            "CLI synthetic body",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "status: imported" in result.output
    assert "content_type: article" in result.output
    assert "source_type: wechat" in result.output
    assert "raw_text:" in result.output
    assert len(list((data_dir / "raw").glob("*/original.txt"))) == 1
    assert len(list((data_dir / "notes").glob("*.md"))) == 1
    assert len(json.loads((data_dir / "index" / "index.json").read_text(encoding="utf-8"))["entries"]) == 1


def test_cli_invalid_url_does_not_create_raw(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PKB_DATA_DIR", str(data_dir))

    result = runner.invoke(
        app,
        [
            "import-wechat-article",
            "https://example.test/article",
            "--title",
            "Synthetic title",
            "--content",
            "Synthetic body",
        ],
    )

    assert result.exit_code != 0
    assert not (data_dir / "raw").exists()
