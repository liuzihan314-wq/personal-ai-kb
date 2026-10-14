from pathlib import Path
import pytest
from pkb.index import IndexBuilder
from pkb.models import UnifiedDocument
from pkb.notes import Note,NoteStorage,NoteService
from pkb.providers import MockAIProvider,UnconfiguredProvider,ProviderNotConfiguredError
from pkb.qa import QAService
from pkb.retrieval.service import RetrievalService
from pkb.retrieval.raw import read_source,source_passages
from pkb.storage import RawStorage
from pkb.ingest.idea import IdeaCardImporter


def test_raw_detail_is_recalled_even_with_incomplete_note(tmp_path):
    root=tmp_path/'alice'
    raw=RawStorage(root/'raw')
    doc=IdeaCardImporter(raw_dir=root/'raw').create('开头只谈工作流。\n'+'背景介绍。'*500+'\n数字人口播可以使用 ExampleAvatar，它适合离线口播。')
    notes=NoteStorage(root/'notes')
    notes.write(Note(document_id=doc.id,source_type='manual',title='普通工作流',summary='摘要未覆盖细节。'))
    idx=IndexBuilder(root/'notes',root/'index/index.json').rebuild()
    hits=RetrievalService(index=idx,raw_dir=root/'raw').search('数字人有什么推荐办法？',embedding_client=None)
    assert hits.candidates[0].document_id==doc.id
    assert hits.candidates[0].evidence.raw
    provider=MockAIProvider()
    result=QAService(index=idx,notes_dir=root/'notes',raw_dir=root/'raw',knowledge_dir=root/'knowledge',provider=provider).answer('数字人口播推荐方案')
    assert result.evidence_level=='notes+raw'
    assert any(s.kind=='raw' and s.citation_id for s in result.sources)
    assert any(e.source_kind=='raw' and 'ExampleAvatar' in e.excerpt for e in result.evidence)
    other=RetrievalService(index=idx,raw_dir=tmp_path/'bob/raw').search('数字人',embedding_client=None)
    assert not other.candidates


def test_source_path_boundary_and_passage_budget(tmp_path):
    raw=tmp_path/'raw';raw.mkdir()
    outside=tmp_path/'outside';outside.mkdir();(outside/'original.txt').write_text('数字人 secret')
    (raw/'bad').symlink_to(outside,target_is_directory=True)
    assert read_source(raw,'bad')==''
    assert read_source(raw,'../outside')==''
    passage,terms=source_passages('数字人案例。'*2000,'数字人',max_chars=2000)
    assert len(passage)<=2000 and terms


def test_default_note_provider_never_silently_creates_mock(tmp_path,monkeypatch):
    monkeypatch.setattr('pkb.notes.service.configured_provider',lambda:UnconfiguredProvider())
    with pytest.raises(ProviderNotConfiguredError):
        NoteService(notes_dir=tmp_path/'notes').generate(UnifiedDocument(id='sample',content_type='idea',source_type='manual',content='真实资料'))
    assert not list((tmp_path/'notes').glob('*.md'))


def test_failed_question_clears_prior_result_and_empty_input_does_not_call():
    from streamlit.testing.v1 import AppTest
    script='''
import streamlit as st
from types import SimpleNamespace
from pkb.ui.app import _render_search_qa_tab
class Service:
    paths=SimpleNamespace(raw_dir='data/raw')
    def answer(self,*args,**kwargs):
        st.session_state['calls']=st.session_state.get('calls',0)+1
        raise RuntimeError('AI 连接失败')
st.session_state.setdefault('search_result',None)
st.session_state.setdefault('qa_result',None)
_render_search_qa_tab(Service())
'''
    app=AppTest.from_string(script).run()
    from types import SimpleNamespace
    app.session_state['qa_result']=SimpleNamespace(status='no_hits',evidence_level='none',answer=None,reason='旧结果',sources=[],evidence=[])
    app.text_area[0].set_value('数字人').run()
    app.button[1].click().run()
    assert app.session_state['qa_result'] is None
    assert app.session_state['calls']==1
    app.text_area[0].set_value(' ').run()
    app.button[1].click().run()
    assert app.session_state['calls']==1
    assert any('请先输入问题' in w.value for w in app.warning)


def test_rebuild_preserves_raw_old_notes_and_identity(tmp_path):
    import json
    from pkb.notes.rebuild import rebuild,digest
    from pkb.notes.markdown import parse_note
    from pkb.providers import OpenAICompatibleProvider
    root=tmp_path/'data'
    document=IdeaCardImporter(raw_dir=root/'raw').create('数字人口播 ExampleAvatar。')
    old=Note(document_id=document.id,source_type='manual',title='私人观点',summary='Mock summary: old',user_note='个人备注')
    NoteStorage(root/'notes').write(old)
    IndexBuilder(root/'notes',root/'index/index.json').rebuild()
    before=digest(root/'raw'/document.id/'original.txt')
    payload={'summary':'数字人口播方案。','key_points':['ExampleAvatar 用于口播。'],'quotes':['数字人口播 ExampleAvatar。'],'tags':['数字人']}
    provider=OpenAICompatibleProvider(model='synthetic',base_url='https://example.test',api_key='synthetic',transport=lambda *args:{'choices':[{'message':{'content':json.dumps(payload)}}]})
    result=rebuild(root,'test',provider=provider)
    assert result['status']=='success'
    after=parse_note((root/'notes'/f'{document.id}.md').read_text())
    assert after.created_at==old.created_at and after.user_note==old.user_note
    assert digest(root/'raw'/document.id/'original.txt')==before
    assert parse_note((root/'derived-backups/test/notes'/f'{document.id}.md').read_text())==old
    assert rebuild(root,'test',provider=provider)['status']=='success'
