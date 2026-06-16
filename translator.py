"""翻译与记忆更新的公共逻辑，供 Step 1（批量并发）与 Step 2（单集）共用。
与 Streamlit 无关，纯函数，方便测试与复用。"""
import json
from pathlib import Path
from openai import OpenAI

from config import estimate_cost, get_api_key

EMPTY_MEMORY = {"episode_count": 0, "characters": {}, "terminology": {}, "style_notes": ""}


def get_client() -> OpenAI | None:
    """返回 OpenAI 客户端；未配置 Key 时返回 None。"""
    api_key = get_api_key()
    return OpenAI(api_key=api_key) if api_key else None


def load_memory(path: Path) -> dict:
    """读取记忆文件，损坏或不存在时返回空记忆。"""
    try:
        if Path(path).exists():
            data = json.load(open(path, "r", encoding="utf-8"))
            return data or dict(EMPTY_MEMORY)
    except (json.JSONDecodeError, OSError):
        pass
    return dict(EMPTY_MEMORY)


def save_memory(memory: dict, path: Path) -> None:
    json.dump(memory, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def _usage_cost(resp, model, fb_in, fb_out) -> float:
    """优先用 API 返回的真实 usage；缺失时回退到分词估算。"""
    if getattr(resp, "usage", None):
        return estimate_cost(resp.usage.prompt_tokens, resp.usage.completion_tokens, model)
    return estimate_cost(fb_in, fb_out, model)


def translate_srt(client: OpenAI, srt_content: str, target_lang: str, model: str, memory: dict):
    """翻译单个 SRT，返回 (译文, 费用)。"""
    system_prompt = f"""You are a professional subtitle translator for short dramas, specializing in localization. Your task is to translate subtitles into {target_lang}.
- **Translate names into a localized form that is natural and culturally appropriate for {target_lang} speakers.** For example, if translating 'John' to Spanish, 'Juan' might be a good option.
- Preserve the original SRT format, including timestamps.
- Maintain the original tone and style of the dialogue.
- Use the provided memory to ensure consistency for character names and terminology.
- Do not add any translator notes or any text outside of the SRT format.

Current memory: {json.dumps(memory, ensure_ascii=False)}
"""
    user_prompt = f"Translate the following subtitles:\n{srt_content}"
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
    )
    translated = resp.choices[0].message.content.strip()
    cost = _usage_cost(resp, model, len(system_prompt.split()) + len(user_prompt.split()), len(translated.split()))
    return translated, cost


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
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": mem_system}, {"role": "user", "content": mem_user}],
        )
    except Exception as e:
        return None, 0.0, f"记忆更新出错: {e}"

    text = resp.choices[0].message.content.strip()
    cost = _usage_cost(resp, model, len(mem_system.split()) + len(mem_user.split()), len(text.split()))
    if not text:
        return None, cost, "记忆更新返回为空"
    try:
        return json.loads(text), cost, None
    except json.JSONDecodeError:
        return None, cost, "记忆更新未能生成有效JSON"
