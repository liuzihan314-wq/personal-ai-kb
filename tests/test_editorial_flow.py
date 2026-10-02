from datetime import datetime, timezone

import pytest

from pkb.index import IndexBuilder
from pkb.notes import Note, NoteStorage
from pkb.providers import MockAIProvider, TopicSuggestion
from pkb.topics import TopicGenerator
from pkb.ui import UIPaths, UIService
from pkb.ui.app import _invalidate_stale_topics


def _note(identity, title, focus):
    return Note(
        document_id=identity, title=title, source_type="manual", content_type="article",
        created_at=datetime(2026, 10, 2, tzinfo=timezone.utc), tags=["AI", focus],
        summary=f"围绕{focus}解释具体做法、适用场景和需要核对的边界，帮助用户完成一次真实任务。",
        key_points=[f"先理解{focus}的作用，再按实际需求选择做法，不要混入其他主题。"],
        source_reference=f"raw:{identity}",
    )


def test_editorial_topics_reject_duplicates_generic_labels_and_unrelated_sources():
    notes = [_note("voice", "声音克隆让视频用自己的声音开口", "声音克隆"), _note("code", "worktree管理代码", "worktree")]
    proposals = [
        TopicSuggestion(title="声音克隆怎么用上自己的音色？", focus="声音克隆", source_ids=["voice"]),
        TopicSuggestion(title="换个说法再讲一次声音克隆", focus="声音克隆", source_ids=["voice"]),
        TopicSuggestion(title="worktree为什么能减少分支切换？", focus="worktree", source_ids=["code"]),
        TopicSuggestion(title="card有什么具体使用技巧？", focus="card", source_ids=["voice"]),
        TopicSuggestion(title="声音克隆与开发配置一起讲", focus="声音克隆", source_ids=["code"]),
        TopicSuggestion(title="声音克隆保证所有视频爆火", focus="声音克隆", source_ids=["missing"]),
    ]
    result = TopicGenerator(notes=notes).generate(provider=MockAIProvider({"generate_topics": proposals}))
    assert [item.focus for item in result.candidates] == ["声音克隆", "worktree"]
    assert all("×" not in item.title for item in result.candidates)
    assert [{source.source_id for source in item.sources} for item in result.candidates] == [{"voice"}, {"code"}]


def test_new_note_invalidates_old_confirmation_and_enters_next_topic_request(tmp_path):
    class CapturingProvider(MockAIProvider):
        def __init__(self):
            super().__init__()
            self.seen = []

        def generate_topics(self, context=(), *, limit=3):
            self.seen.append({item.document_id for item in context})
            return [TopicSuggestion(title="声音克隆怎么用上自己的音色？", focus="声音克隆", source_ids=["voice"])]

    paths = UIPaths.from_data_dir(tmp_path)
    storage = NoteStorage(paths.notes_dir)
    storage.write(_note("voice", "声音克隆实践", "声音克隆"))
    IndexBuilder(paths.notes_dir, paths.index_path).rebuild()
    provider = CapturingProvider()
    service = UIService(paths, provider=provider)
    result = service.generate_topics()
    revision = service.library_revision()
    state = dict(topics_result=result, topics_revision=revision, script_result="old draft", topic_selection_confirmed=True, topic_select=result.candidates[0].title)
    assert not _invalidate_stale_topics(state, revision)
    storage.write(_note("new", "新增声音克隆细节", "声音克隆"))
    IndexBuilder(paths.notes_dir, paths.index_path).rebuild()
    assert _invalidate_stale_topics(state, service.library_revision())
    assert state["topics_result"] is None and state["script_result"] is None
    assert state["topic_select"] == "" and not state["topic_selection_confirmed"]
    service.generate_topics()
    assert provider.seen == [{"voice"}, {"voice", "new"}]


def test_topic_revision_is_scoped_to_the_current_user(tmp_path):
    alice = UIService(UIPaths.from_data_dir(tmp_path, user_id="u_" + "a" * 64), provider=MockAIProvider())
    bob = UIService(UIPaths.from_data_dir(tmp_path, user_id="u_" + "b" * 64), provider=MockAIProvider())
    revision = alice.library_revision()
    NoteStorage(bob.paths.notes_dir).write(_note("bob-note", "声音克隆", "声音克隆"))
    assert alice.library_revision() == revision


@pytest.mark.parametrize("noise", ["本文是AI学习之路第20篇。", "来源十二：", "Summary:"])
def test_article_introductions_fail_copy_quality_gate(noise, spoken_copy):
    from pkb.scripts.service import _script_quality_issues

    assert any("文章介绍" in item for item in _script_quality_issues(noise + spoken_copy))


def test_spoken_copy_typography_does_not_depend_on_model_spacing():
    from pkb.scripts.service import _format_spoken_copy

    assert _format_spoken_copy("在worktree里写CLAUDE.md，3步完成——别忘了commit。") == "在 worktree 里写 CLAUDE.md，3 步完成--别忘了 commit。"
