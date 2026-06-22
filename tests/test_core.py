"""纯函数单元测试。

运行方式（任选其一）：
    python tests/test_core.py        # 无需 pytest，直接运行
    pytest tests/                    # 装了 pytest 也可
"""
import os
import sys

# 让测试能从仓库根目录导入各模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import translator as T
from step1 import _natural_sort_key
import step3


def test_estimate_cost():
    # 1M 输入 + 1M 输出 @ gpt-5.4-mini = 0.75 + 4.50
    assert abs(config.estimate_cost(1_000_000, 1_000_000, "gpt-5.4-mini") - 5.25) < 1e-9
    # 未知模型返回 0
    assert config.estimate_cost(1000, 1000, "no-such-model") == 0.0


def test_natural_sort():
    files = ["ep10.srt", "ep2.srt", "ep1.srt", "ep21.srt"]
    assert sorted(files, key=_natural_sort_key) == ["ep1.srt", "ep2.srt", "ep10.srt", "ep21.srt"]


def test_clean_srt():
    raw = "```srt\n1\n00:00:01,000 --> 00:00:02,000\nHello\n```"
    cleaned = T._clean_srt(raw)
    assert not cleaned.startswith("```") and "Hello" in cleaned


SRT = "\n\n".join(
    f"{i}\n00:00:0{i},000 --> 00:00:0{i+1},000\nLine {i}" for i in range(1, 6)
)


def test_chunking():
    assert T._parse_srt(SRT) is not None
    saved = config.CHUNK_CUES
    try:
        config.CHUNK_CUES = 2
        assert len(T._chunk_srt(SRT)) == 3  # 5 条字幕，每块 2 条 -> 3 块
        config.CHUNK_CUES = 100
        assert len(T._chunk_srt(SRT)) == 1  # 不超阈值则单块
    finally:
        config.CHUNK_CUES = saved


def test_trim_memory():
    mem = {"characters": {str(i): i for i in range(config.MAX_MEMORY_ITEMS + 50)},
           "terminology": {}, "style_notes": "x" * (config.MAX_STYLE_NOTES + 100)}
    T.trim_memory(mem)
    assert len(mem["characters"]) == config.MAX_MEMORY_ITEMS
    assert len(mem["style_notes"]) == config.MAX_STYLE_NOTES


def test_wrap_latin():
    if not step3.default_font_path:
        return  # 无可用字体时跳过
    out = step3.wrap_text_pil("alpha beta gamma delta epsilon zeta eta theta", step3.default_font_path, 48, 300)
    assert "\n" in out  # 应当发生换行
    assert out.replace("\n", " ") == "alpha beta gamma delta epsilon zeta eta theta"  # 不丢词


def test_wrap_cjk_and_kinsoku():
    if not step3.default_font_path:
        return
    out = step3.wrap_text_pil("这是一个很长的句子需要换行测试，看看标点会不会跑到行首。", step3.default_font_path, 48, 280)
    lines = out.split("\n")
    assert len(lines) > 1  # CJK 应按字符换行
    assert all(ln and ln[0] not in step3._LEADING_FORBIDDEN for ln in lines)  # 避头尾
    assert all(not step3._is_combining_mark(ln[0]) for ln in lines if ln)


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
