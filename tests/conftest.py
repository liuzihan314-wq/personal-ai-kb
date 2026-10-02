"""Shared pytest fixtures for isolated settings-based tests."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from pkb.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Keep environment-driven settings isolated between test cases."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def spoken_copy() -> str:
    """A fixed publishable draft for successful provider-contract tests."""

    return (
        "很多人装了一堆 AI 工具，忙了一天，重复劳动却一点没少。你有没有遇到过这种情况？"
        "今天聊 AI 工作流：把 AI 工具组合成可复用的效率流程，先把任务拆成流程，再决定工具。\n\n"
        "假设你每周都要整理一次会议记录。不要一上来就问哪个模型最强，先把事情写清楚："
        "你手里拿到的是录音还是文字？最后需要一份纪要，还是一张待办清单？同一个问题，"
        "输入和结果不同，做法就会不同。先确定你需要的结果，才能判断哪些步骤值得交给 AI。\n\n"
        "接下来，把重复动作拆开。哪些是整理材料，哪些是确认信息，哪些需要你作判断？"
        "整理和改写可以让工具协助，但涉及别人说了什么、事情由谁负责，你得回头核对。"
        "把这个分工说清楚，比增加工具数量更有用。否则你只是把一堆操作换成了另一堆操作。\n\n"
        "然后，挑一个最小的真实任务试试。不要同时改十个环节，先改最耗时间的那个。"
        "把前后的做法留住，看看哪里节省了时间，哪里反而增加了核对负担。如果结果不稳定，"
        "就检查输入是否完整、要求是否具体，而不是马上再换一个工具。\n\n"
        "还有一个容易忽略的地方：第一次成功不等于以后都能复用。把你给的输入、判断标准"
        "和最后留下的结果记下来，换一份材料再试一次。遇到不同情况也能讲清楚为什么这么做，"
        "这套做法才真正属于你。所谓流程，不是画一张漂亮的图，而是下一次还能照着完成。\n\n"
        "最后，别把核对环节省掉。自动化要嵌入工作流，先验证具体任务的收益。一个环节看起来"
        "很快，如果后面要花更多时间返工，它就没有帮你省事。让结果说话，哪一步有用就留下，"
        "哪一步只是增加负担就继续改。\n\n"
        "今天就选一件每周都会重复的小事，先把过程写出来，再试着改其中一个环节。"
        "你需要的不是更长的工具名单，而是一种能解释、能复用、也能继续改的做法。"
    )
@pytest.fixture
def tmp_path() -> Path:
    """Override pytest's default tmp_path to stay inside the project worktree.

    The brokered sandbox denies writes under the system temp root for some
    test files, so all test scratch space is created under ``tests/_tmp``.
    """

    base = Path(__file__).parent / "_tmp"
    base.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=base, prefix="pytest-") as directory:
        yield Path(directory)
