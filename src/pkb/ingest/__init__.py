"""Input adapters for the personal knowledge base."""

from pkb.ingest.idea import IdeaCardError, IdeaCardImporter, create_idea
from pkb.ingest.pdf import PDFImportError, PDFImporter, UnsupportedPDFError, import_pdf
from pkb.ingest.wechat import (
    FetchedWeChatArticle,
    InvalidWeChatURL,
    MANUAL_REQUIRED_MESSAGE,
    MANUAL_REQUIRED_STATUS,
    ManualImportRequired,
    WeChatArticleImporter,
    WeChatArticleService,
    WeChatImportError,
    WeChatImportResult,
    WeChatManualImportError,
    WeChatURLValidationError,
    import_manual_wechat_article,
    import_wechat_article,
    is_wechat_article_url,
    normalize_wechat_article_url,
)

__all__ = [
    "IdeaCardError",
    "IdeaCardImporter",
    "FetchedWeChatArticle",
    "InvalidWeChatURL",
    "MANUAL_REQUIRED_MESSAGE",
    "MANUAL_REQUIRED_STATUS",
    "ManualImportRequired",
    "PDFImportError",
    "PDFImporter",
    "UnsupportedPDFError",
    "WeChatArticleImporter",
    "WeChatArticleService",
    "WeChatImportError",
    "WeChatImportResult",
    "WeChatManualImportError",
    "WeChatURLValidationError",
    "create_idea",
    "import_manual_wechat_article",
    "import_pdf",
    "import_wechat_article",
    "is_wechat_article_url",
    "normalize_wechat_article_url",
]
