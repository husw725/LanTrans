"""集中配置：模型、价格、语言、路径、压缩参数与通用辅助函数。
改价 / 换模型 / 加语言只需改这一个文件。"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- 路径 ---
TEMP_DIR = Path("./temp")
TEMP_DIR.mkdir(exist_ok=True)
STYLE_FILE = TEMP_DIR / "subtitle_style.json"


def memory_path(lang: str) -> Path:
    """某语言的翻译记忆文件路径。"""
    return TEMP_DIR / f"drama_memory_{lang}.json"


# --- 模型与价格（美元 / 每百万 token），核对于 2026-06 ---
# 来源：openai.com/api/pricing 及多家聚合站。换模型只改这里。
MODEL_COST = {
    "gpt-5.4": {"input": 2.50, "output": 15.0},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
    # 旧款保留以便回退对比
    "gpt-5.1": {"input": 1.25, "output": 10.0},
    "gpt-5-mini": {"input": 0.25, "output": 2.0},
    "gpt-5-nano": {"input": 0.05, "output": 0.40},
}

# 下拉框可选项（推荐项排第一）
TRANSLATE_MODELS = ["gpt-5.4-mini", "gpt-5.4", "gpt-5.1", "gpt-5-mini", "gpt-5-nano"]
MEMORY_MODELS = ["gpt-5.4-nano", "gpt-5-nano", "gpt-5.4-mini"]
DEFAULT_TRANSLATE_MODEL = "gpt-5.4-mini"
DEFAULT_MEMORY_MODEL = "gpt-5.4-nano"

# --- 语言表 ---
LANG_OPTIONS = {
    "阿拉伯语 (Arabic)": "Arabic", "英语 (English)": "English", "西班牙语 (Spanish)": "Spanish",
    "葡萄牙语 (Portuguese)": "Portuguese", "德语 (German)": "German", "法语 (French)": "French",
    "意大利语 (Italian)": "Italian", "印尼语 (Indonesian)": "Indonesian", "印地语 (Hindi)": "Hindi",
    "泰语 (Thai)": "Thai", "马来语 (Malay)": "Malay", "日本语 (Japanese)": "Japanese",
    "韩语 (Korean)": "Korean", "中文（繁体） (Traditional Chinese)": "Traditional Chinese",
    "中文（简体） (Simplified Chinese)": "Simplified Chinese",
}

# --- 视频压缩 ---
CRF_OPTIONS = [16, 18, 20, 22, 24, 26, 28, 30]
DEFAULT_CRF = 22


def get_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """按真实 token 数估算费用。未知模型返回 0。"""
    if model not in MODEL_COST:
        return 0.0
    c = MODEL_COST[model]
    return input_tokens / 1_000_000 * c["input"] + output_tokens / 1_000_000 * c["output"]
