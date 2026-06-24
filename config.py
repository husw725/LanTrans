"""集中配置：模型、价格、语言、路径、压缩参数与通用辅助函数。
改价 / 换模型 / 加语言只需改这一个文件。"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# MoviePy 在 import 时会直接读取 IMAGEMAGICK_BINARY 环境变量；若它指向不存在的
# 路径（例如把 Windows 的 ImageMagick 路径带到 macOS/Linux），moviepy 导入即崩溃。
# 这里清理掉无效值，让 moviepy 自动探测。务必保证本模块先于 moviepy 被导入。
_im = os.environ.get("IMAGEMAGICK_BINARY")
if _im and not os.path.exists(_im):
    os.environ.pop("IMAGEMAGICK_BINARY", None)

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

# 字幕样式预览的示例文本（按语言），用于 Step 3 实时预览。
# 每句都足够长以演示换行效果。键为 LANG_OPTIONS 的值。
PREVIEW_SAMPLES = {
    "English": "Subtitle preview — this line is long enough to show wrapping.",
    "Spanish": "Vista previa de subtítulos: esta línea es lo bastante larga para ver el ajuste.",
    "Portuguese": "Pré-visualização de legendas: esta linha é longa o suficiente para mostrar a quebra.",
    "German": "Untertitel-Vorschau – diese Zeile ist lang genug, um den Umbruch zu zeigen.",
    "French": "Aperçu des sous-titres : cette ligne est assez longue pour afficher le retour.",
    "Italian": "Anteprima dei sottotitoli: questa riga è abbastanza lunga da mostrare l'a capo.",
    "Indonesian": "Pratinjau subtitle — baris ini cukup panjang untuk menampilkan pembungkusan.",
    "Malay": "Pratonton sari kata — baris ini cukup panjang untuk menunjukkan pembalutan teks.",
    "Arabic": "معاينة الترجمة — هذا السطر طويل بما يكفي لإظهار التفاف النص.",
    "Hindi": "उपशीर्षक पूर्वावलोकन — यह पंक्ति रैपिंग दिखाने के लिए पर्याप्त लंबी है।",
    "Thai": "ตัวอย่างคำบรรยาย — บรรทัดนี้ยาวพอที่จะแสดงการตัดบรรทัด",
    "Japanese": "字幕プレビュー：この行は折り返しを確認できる長さです。",
    "Korean": "자막 미리보기 — 이 줄은 줄바꿈을 보여줄 만큼 충분히 깁니다.",
    "Traditional Chinese": "字幕預覽：這段文字會展示換行效果。",
    "Simplified Chinese": "字幕预览：这段文字会展示换行效果。",
}

# 非拉丁文字语言：默认 Arial 字体无法渲染，需上传对应字体。
NON_LATIN_LANGS = {"Arabic", "Hindi", "Thai", "Japanese", "Korean",
                   "Traditional Chinese", "Simplified Chinese"}

# --- 翻译稳健性 ---
RETRY_ATTEMPTS = 4            # OpenAI 调用失败时的重试次数
RETRY_BASE_DELAY = 2.0        # 指数退避基数（秒）：2, 4, 8...
CHUNK_CUES = 40              # 单次请求的最大字幕条数，超过则分块翻译，防止输出被截断
MAX_MEMORY_ITEMS = 150       # 翻译记忆中 characters / terminology 各自保留的最大条目数
MAX_STYLE_NOTES = 800        # style_notes 的最大字符数
TRANSLATE_TEMPERATURE = None  # 0~1 可降低随机性；None=用模型默认。注意 GPT-5 系列可能不支持自定义温度

# --- 字幕样式预设（短剧常用风格，一键套用）---
STYLE_PRESETS = {
    "白字黑边（经典）": {"font_color": "#FFFFFF", "stroke_color": "#000000", "stroke_width": 2,
                         "bold": 1, "shadow_opacity": 0.5, "shadow_color": "#000000",
                         "shadow_offset": (0, 2), "bg_enabled": False},
    "黄字黑边（短剧常用）": {"font_color": "#FFE000", "stroke_color": "#000000", "stroke_width": 2,
                            "bold": 2, "shadow_opacity": 0.6, "shadow_color": "#000000",
                            "shadow_offset": (0, 2), "bg_enabled": False},
    "底部半透明色块": {"font_color": "#FFFFFF", "stroke_color": "#000000", "stroke_width": 0,
                       "bold": 1, "shadow_opacity": 0.0, "bg_enabled": True,
                       "bg_color": "#000000", "bg_opacity": 0.5, "bg_padding": 14},
    "粗体大字（标题）": {"font_color": "#FFFFFF", "stroke_color": "#000000", "stroke_width": 3,
                        "bold": 4, "shadow_opacity": 0.4, "shadow_color": "#000000",
                        "shadow_offset": (0, 3), "bg_enabled": False},
}

# 颜色快捷预设（文字色 / 描边色）
COLOR_PRESETS = {
    "白字黑边": ("#FFFFFF", "#000000"),
    "黄字黑边": ("#FFE000", "#000000"),
    "黑字白边": ("#000000", "#FFFFFF"),
}

# 内置字体目录：把 .ttf/.ttc/.otf 放进来即可在界面下拉选用（中文/日文等放这里最方便）
FONTS_DIR = Path("./fonts")

# --- 视频编码 ---
CRF_OPTIONS = [16, 18, 20, 22, 24, 26, 28, 30]
DEFAULT_CRF = 22
ENCODE_PRESETS = ["veryfast", "fast", "medium", "slow"]  # 越靠右越慢、压缩率越高
DEFAULT_PRESET = "medium"
# libx264 preset → NVENC preset(p1 最快 … p7 最慢质量最好）
NVENC_PRESET_MAP = {"veryfast": "p1", "fast": "p3", "medium": "p5", "slow": "p7"}


def get_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """按真实 token 数估算费用。未知模型返回 0。"""
    if model not in MODEL_COST:
        return 0.0
    c = MODEL_COST[model]
    return input_tokens / 1_000_000 * c["input"] + output_tokens / 1_000_000 * c["output"]
