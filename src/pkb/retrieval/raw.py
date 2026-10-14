"""Bounded, user-scoped source passages; summaries do not replace originals."""

from pathlib import Path
import re
from pkb.index.keywords import tokenize_text


def source_passages(text: str, query: str, *, max_chars: int = 3000) -> tuple[str, list[str]]:
    intent = query.casefold()
    for phrase in ('有什么', '有没有', '推荐', '方案', '办法', '怎么', '如何', '哪些', '什么', '帮我', '一下'):
        intent = intent.replace(phrase, ' ')
    terms = set(tokenize_text(intent))
    terms.update(run[i:i+3] for run in re.findall(r'[\u4e00-\u9fff]+', intent)
                 for i in range(max(0, len(run)-2)))
    if not terms:
        return '', []
    ranked = []
    for pos in range(0, len(text), 700):
        chunk = text[pos:pos+1000]
        matches = sorted(term for term in terms if term in chunk.casefold())
        if matches:
            ranked.append((sum(len(t)**2 for t in matches), pos, chunk, matches))
    chosen = sorted(sorted(ranked, key=lambda item: (-item[0], item[1]))[:3], key=lambda item: item[1])
    result = '\n\n'.join(item[2] for item in chosen)[:max_chars]
    return result, sorted({term for item in chosen for term in item[3]})


def read_source(raw_dir: Path, document_id: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9_-]+', document_id):
        return ''
    root = raw_dir.resolve()
    folder = raw_dir / document_id
    for filename in ('extracted.txt', 'original.txt'):
        path = folder / filename
        if path.is_file():
            if path.is_symlink() or folder.is_symlink() or not path.resolve().is_relative_to(root):
                return ''
            return path.read_text(encoding='utf-8')
    return ''
