"""翻译与记忆更新的公共逻辑，供 Step 1（批量并发）与 Step 2（单集）共用。
与 Streamlit 无关，纯函数，方便测试与复用。

健壮性设计：
- OpenAI 调用带指数退避重试（限流 / 超时 / 5xx）。
- 长 SRT 按字幕条数分块翻译，避免输出被截断。
- 译文落盘前清洗 markdown 围栏并用 pysrt 校验、重排序号。
- 翻译记忆条目设上限，避免逐集膨胀。
"""
import json
import re
import time

import pysrt
from openai import (OpenAI, RateLimitError, APITimeoutError,
                    APIConnectionError, InternalServerError)

import config

EMPTY_MEMORY = {"episode_count": 0, "characters": {}, "terminology": {}, "style_notes": ""}
_RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)


def get_client() -> OpenAI | None:
    """返回 OpenAI 客户端；未配置 Key 时返回 None。"""
    api_key = config.get_api_key()
    return OpenAI(api_key=api_key) if api_key else None


# ---------------- 记忆读写 ----------------

def load_memory(path) -> dict:
    """读取记忆文件，损坏或不存在时返回空记忆。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data or dict(EMPTY_MEMORY)
    except (json.JSONDecodeError, OSError):
        return dict(EMPTY_MEMORY)


def save_memory(memory: dict, path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def trim_memory(memory: dict) -> dict:
    """裁剪记忆，避免逐集累积导致 prompt 无限膨胀。就地修改并返回。"""
    for key in ("characters", "terminology"):
        d = memory.get(key)
        if isinstance(d, dict) and len(d) > config.MAX_MEMORY_ITEMS:
            memory[key] = dict(list(d.items())[-config.MAX_MEMORY_ITEMS:])
    notes = memory.get("style_notes")
    if isinstance(notes, str) and len(notes) > config.MAX_STYLE_NOTES:
        memory["style_notes"] = notes[-config.MAX_STYLE_NOTES:]
    return memory


# ---------------- 底层调用 ----------------

def _chat(client: OpenAI, model: str, system: str, user: str):
    """带指数退避重试的 chat.completions 调用。"""
    last_err = None
    for attempt in range(config.RETRY_ATTEMPTS):
        try:
            kwargs = dict(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            if config.TRANSLATE_TEMPERATURE is not None:
                kwargs["temperature"] = config.TRANSLATE_TEMPERATURE
            return client.chat.completions.create(**kwargs)
        except _RETRYABLE as e:
            last_err = e
            if attempt < config.RETRY_ATTEMPTS - 1:
                time.sleep(config.RETRY_BASE_DELAY * (2 ** attempt))
    raise last_err


def _usage_cost(resp, model, fb_in, fb_out) -> float:
    """优先用 API 返回的真实 usage；缺失时回退到分词估算。"""
    if getattr(resp, "usage", None):
        return config.estimate_cost(resp.usage.prompt_tokens, resp.usage.completion_tokens, model)
    return config.estimate_cost(fb_in, fb_out, model)


# ---------------- SRT 清洗与分块 ----------------

def _clean_srt(text: str) -> str:
    """去掉模型可能添加的 markdown 围栏与前后空白。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)
    return text.strip()


def _parse_srt(text: str):
    """尝试解析为 SRT；成功且非空返回 SubRipFile，否则 None。"""
    try:
        subs = pysrt.from_string(text)
        return subs if len(subs) else None
    except Exception:
        return None


def _chunk_srt(srt_content: str):
    """把 SRT 拆成若干块（每块至多 CHUNK_CUES 条字幕）。解析失败则整体作为一块。"""
    source = _parse_srt(srt_content)
    if source is None:
        return [srt_content]
    cues = list(source)
    if len(cues) <= config.CHUNK_CUES:
        return [srt_content]
    return ["\n".join(str(c) for c in cues[i:i + config.CHUNK_CUES])
            for i in range(0, len(cues), config.CHUNK_CUES)]


def _system_prompt(target_lang: str, memory: dict) -> str:
    return f"""You are a professional subtitle translator for short dramas, specializing in localization. Your task is to translate subtitles into {target_lang}.
- **Translate names into a localized form that is natural and culturally appropriate for {target_lang} speakers.** For example, if translating 'John' to Spanish, 'Juan' might be a good option.
- Preserve the original SRT format exactly, including the index numbers and timestamps.
- Maintain the original tone and style of the dialogue.
- Use the provided memory to ensure consistency for character names and terminology.
- Do not add any translator notes, explanations, or markdown fences — output raw SRT only.

Current memory: {json.dumps(memory, ensure_ascii=False)}
"""


# ---------------- 对外 API ----------------

def translate_srt(client: OpenAI, srt_content: str, target_lang: str, model: str, memory: dict):
    """翻译单个 SRT（必要时分块），返回 (译文, 费用)。译文已清洗并重排序号。"""
    system_prompt = _system_prompt(target_lang, memory)
    chunks = _chunk_srt(srt_content)

    parts, total_cost = [], 0.0
    for chunk in chunks:
        user_prompt = f"Translate the following subtitles:\n{chunk}"
        part = ""
        # 单块若解析失败最多重试一次（覆盖模型偶发的格式跑偏）
        for attempt in range(2):
            resp = _chat(client, model, system_prompt, user_prompt)
            part = _clean_srt(resp.choices[0].message.content)
            total_cost += _usage_cost(resp, model, len(system_prompt.split()) + len(user_prompt.split()), len(part.split()))
            if _parse_srt(part) is not None or attempt == 1:
                break
        parts.append(part)

    merged = "\n\n".join(parts)
    # 校验 + 重排序号，得到干净连续的 SRT
    parsed = _parse_srt(merged)
    if parsed is not None:
        parsed.clean_indexes()
        merged = "\n".join(str(c) for c in parsed)
    return merged, total_cost


def update_memory(client: OpenAI, translated_srt: str, memory: dict, model: str):
    """根据译文更新记忆。返回 (新记忆或None, 费用, 错误信息或None)。
    任何失败都不抛异常，调用方据此决定是否保留旧记忆。"""
    mem_system = "You are an assistant that updates a JSON object. ONLY output a valid, raw JSON object without explanations or markdown."
    mem_user = f"""Analyze the translated SRT and update the memory JSON.
- Identify character names and any specific terminology.
- If a name has been localized, store both the original and the localized version in the 'characters' section.
- Update the 'terminology' and 'style_notes' as needed.
- Return the complete, updated JSON object.

Previous memory: {json.dumps(memory, ensure_ascii=False)}
Translated SRT:
{translated_srt}
"""
    try:
        resp = _chat(client, model, mem_system, mem_user)
    except Exception as e:
        return None, 0.0, f"记忆更新出错: {e}"

    text = _clean_srt(resp.choices[0].message.content)
    cost = _usage_cost(resp, model, len(mem_system.split()) + len(mem_user.split()), len(text.split()))
    if not text:
        return None, cost, "记忆更新返回为空"
    try:
        return json.loads(text), cost, None
    except json.JSONDecodeError:
        return None, cost, "记忆更新未能生成有效JSON"
