import streamlit as st
from openai import OpenAI
# 确保您有一个名为 key.py 的文件，其中包含 API_KEY = "sk-..."
from key import key as API_KEY 
import os
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import logging

# 配置日志，便于后台调试和查看文件读写状态
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 成本配置 ---
MODEL_COST = {
    "gpt-5.2": {"input": 1.75, "output": 14.0},
    "gpt-5.1": {"input": 1.25, "output": 10.0},
    "gpt-5-mini": {"input": 0.25, "output": 2.0},
    "gpt-5-nano": {"input": 0.05, "output": 0.4},
}

# --- 辅助函数：成本、排序、文件安全读写 ---

def estimate_cost(input_tokens, output_tokens, model):
    """估算翻译成本 (USD) - 基于每百万 token 价格"""
    return (input_tokens / 1_000_000 * MODEL_COST[model]["input"]) + \
           (output_tokens / 1_000_000 * MODEL_COST[model]["output"])

def natural_sort_key(filename):
    """自然排序函数，确保 1.srt, 2.srt, ..., 10.srt 的正确顺序"""
    name, ext = os.path.splitext(filename)
    parts = re.split(r'(\d+)', name)
    key = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part)
    return key

def extract_episode_info(filename):
    """
    从文件名中提取数字部分（集数）和原始数字长度。
    例如 'Ep_010.srt' -> ('10', 3)
    """
    stem = Path(filename).stem
    # 找到所有数字序列
    matches = re.findall(r'(\d+)', stem)
    
    if matches:
        # 默认取第一个数字序列作为集数
        number_str = matches[0]
        # 返回数字字符串和其原始长度（用于 zfill 补零）
        return number_str, len(number_str)
    
    return None, 0

def get_memory_path(temp_dir, lang, episode_number, original_length):
    """生成记忆文件的完整路径，确保集数使用原始长度补零"""
    if episode_number == 0:
        # 第一集的上一集（第 0 集）特殊处理，用于初始化
        episode_str = "0".zfill(original_length)
    else:
        episode_str = str(episode_number).zfill(original_length)
        
    return temp_dir / f"memory_{lang}_{episode_str}.json"

def safe_json_dump(data, path: Path):
    """
    安全地写入 JSON 文件，通过写入临时文件再重命名，保证文件写入的原子性。
    """
    temp_path = path.with_suffix('.tmp')
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_path.rename(path)
        return True
    except Exception as e:
        logging.error(f"❌ 严重错误: 无法安全写入 JSON 文件 {path}: {e}")
        if temp_path.exists():
            temp_path.unlink()
        return False

def load_memory(memory_path: Path):
    """安全加载记忆文件，如果文件损坏或不存在，则返回空字典"""
    if memory_path.exists():
        try:
            with open(memory_path, "r", encoding="utf-8") as f:
                memory = json.load(f)
            if "characters" not in memory or not isinstance(memory["characters"], dict):
                logging.warning(f"⚠️ 记忆文件 {memory_path} 结构异常。返回空记忆。")
                return {"characters": {}}
            logging.info(f"✅ 成功加载记忆文件 {memory_path}")
            return memory
        except Exception as e:
            logging.warning(f"⚠️ 记忆文件 {memory_path} 损坏或格式错误。将重置。错误: {e}")
            return {"characters": {}}
    return {"characters": {}}

# --- 核心翻译逻辑 ---

def process_language(lang, input_dir, output_root, srt_files, translate_model, client, temp_dir):
    """
    处理单一目标语言的所有 SRT 文件的翻译和记忆更新 (按集链式管理记忆)。
    """
    output_dir = Path(output_root) / lang
    output_dir.mkdir(parents=True, exist_ok=True)

    results = [f"--- 开始处理语言: **{lang}** ---"]
    total_cost = 0.0
    
    # 获取原始文件的数字长度，以便在生成记忆文件时正确补零 (e.g., 01, 02...)
    # 假设所有文件的数字长度一致，基于第一个 SRT 文件
    if srt_files:
        _, original_len = extract_episode_info(srt_files[0])
    else:
        original_len = 1

    for srt_file in srt_files:
        
        # 1. 确定集数和记忆文件路径
        episode_number_str, _ = extract_episode_info(srt_file)
        
        if not episode_number_str or not episode_number_str.isdigit():
            results.append(f"❌ {lang} - `{srt_file}` 无法识别集数，跳过此文件。")
            continue
            
        current_episode = int(episode_number_str)
        
        # 定义本集应该读取的【前一集】的记忆路径
        input_memory_path = get_memory_path(temp_dir, lang, current_episode - 1, original_len)
        
        # 定义本集翻译后应该保存的【本集】的记忆路径
        output_memory_path = get_memory_path(temp_dir, lang, current_episode, original_len)
        
        input_path = os.path.join(input_dir, srt_file)
        output_path = output_dir / srt_file

        # 如果本集的翻译结果和记忆文件都已存在，则跳过
        if output_path.exists() and output_memory_path.exists():
            results.append(f"跳过 {lang} - `{srt_file}` (已完成)")
            continue

        # 2. 加载上一集的只读记忆
        memory = load_memory(input_memory_path)
        current_memory_json = json.dumps(memory, ensure_ascii=False)
        
        # 3. 读取 SRT 内容
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                srt_content = f.read()
        except Exception as e:
            results.append(f"❌ {lang} - `{srt_file}` 读取失败: {e}")
            continue

        # 4. 准备 Prompt
        system_prompt = f"""
You are a professional subtitle translator for short dramas, translating into {lang}.

==============================
CORE GOAL
==============================
Your primary goal is to produce subtitles that feel as if they were
ORIGINALLY written in the target language and culture.
Character names MUST look and feel like real LOCAL names.

==============================
CHARACTER NAME MEMORY RULES
==============================
1. You MUST use memory['characters'] to keep character names consistent across episodes.
2. Memory keys MUST be the ORIGINAL character names exactly as they appear in the source SRT.
3. If an original name already exists in memory:
   - You MUST reuse the mapped translated name EXACTLY.
   - Do NOT alter spelling, spacing, or name length.
4. You are STRICTLY FORBIDDEN from creating a new name for an existing character.

==============================
NEW CHARACTER NAME LOCALIZATION (VERY IMPORTANT)
==============================
5. For characters NOT yet in memory, you MUST create a FULLY LOCALIZED name
   that looks natural for native speakers of {lang}.

6. The localized name MUST:
   - Look like a REAL, commonly used local name in movies or TV shows.
   - Match the character's gender, age, and personality if implied by dialogue.
   - Feel natural and believable to a native audience at first glance.

7. Phonetic similarity rules (OPTIONAL, LIMITED USE):
   - You MAY choose a local name that has a SIMILAR SOUND or RHYTHM to the original name.
   - This similarity is ONLY a reference, NOT a goal.
   - The final name MUST still look 100% like a native name.

8. STRICTLY FORBIDDEN:
   - Using pinyin or romanized Chinese (e.g. "Xiaoyu", "Ling", "Zhaoyang").
   - Direct phonetic transliteration.
   - Names that look foreign, artificial, or non-native.
   - Keeping Chinese name order or structure.

9. If a name does NOT look like a real native name for {lang},
   then it is WRONG even if it sounds similar.

10. Once a new localized name is chosen:
    - It becomes FINAL and IMMUTABLE.
    - It MUST be used consistently in all future episodes.

==============================
OUTPUT FORMAT (STRICT)
==============================
11. Output ONLY:
    - The translated subtitle content wrapped in <SRT>...</SRT>
    - A JSON object of ONLY newly added character mappings wrapped in <MEMORY_DELTA>...</MEMORY_DELTA>

12. Do NOT:
    - Explain your choices
    - Output notes, comments, or analysis
    - Output the full memory

==============================
CURRENT MEMORY
==============================
{current_memory_json}
"""

        user_prompt = f"Translate the following subtitles:\n{srt_content}"

        translated_content = None
        
        # 5. 翻译重试逻辑
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=translate_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.1
                )
                translated_content = resp.choices[0].message.content.strip()
                
                # 成本估算
                input_tokens = len(system_prompt.split()) + len(user_prompt.split())
                output_tokens = len(translated_content.split())
                total_cost += estimate_cost(input_tokens, output_tokens, translate_model)
                break
            except Exception as e:
                logging.warning(f"API 调用失败 {lang} - `{srt_file}` (第 {attempt + 1}/3 次): {e}")
                time.sleep(2)
        else:
            results.append(f"❌ {lang} - `{srt_file}` 翻译失败 (3 次重试)")
            continue

        # 6. 解析 SRT 与 memory_delta
        srt_match = re.search(r"<SRT>(.*?)</SRT>", translated_content, re.S)
        mem_match = re.search(r"<MEMORY_DELTA>(.*?)</MEMORY_DELTA>", translated_content, re.S)
        
        if not srt_match:
            results.append(f"⚠️ {lang} - `{srt_file}` 警告：未找到 <SRT> 标签。")

        # 7. 处理 Memory Delta 并更新内存
        delta_found = False
        if mem_match:
            try:
                delta_json_str = mem_match.group(1).strip()
                delta = json.loads(delta_json_str)

                if isinstance(delta, dict):
                    for raw_key, raw_val in delta.items():
                        key = str(raw_key).strip()
                        val = str(raw_val).strip()
                        
                        if key and val and key not in memory["characters"]:
                             memory["characters"][key] = val
                             logging.info(f"[{lang} - {srt_file}] 新增角色: {key} -> {val}")
                             delta_found = True
                
            except Exception as e:
                results.append(f"⚠️ {lang} - `{srt_file}` 警告：MEMORY_DELTA 解析失败: {e}")

        # 8. 安全保存本集的最终记忆 (用于下一集读取)
        if srt_match or delta_found:
            if not safe_json_dump(memory, output_memory_path):
                 results.append(f"❌ {lang} - `{srt_file}` 错误：本集记忆文件保存失败！")

        # 9. 保存翻译结果
        if srt_match:
            final_srt = srt_match.group(1).strip()
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(final_srt)
                results.append(f"✅ 完成 {lang} - `{srt_file}`, 当前累计费用 ${total_cost:.4f}")
            except Exception as e:
                results.append(f"❌ {lang} - `{srt_file}` 文件写入失败: {e}")
        
    results.append(f"💰 **{lang} 总费用: ${total_cost:.4f}**")
    return results

# --- Streamlit UI 主函数 ---

def run():
    # 确保 API 密钥存在
    if 'API_KEY' not in globals() or not API_KEY:
        st.error("❌ API 密钥 (API_KEY) 未加载或为空。请检查 key.py 文件。")
        return
        
    client = OpenAI(api_key=API_KEY)
    TEMP_DIR = Path("./temp")
    TEMP_DIR.mkdir(exist_ok=True)

    st.title("🎬 SRT 剧集批量多语言翻译工具")
    st.header("Step 1: 批量多语言翻译 SRT（按集链式记忆）")
    st.markdown("---")

    input_dir = st.text_input("📁 输入 SRT 文件夹路径 (包含所有剧集 SRT 文件)：", value="./input_srtList")
    output_root = st.text_input("📂 输出翻译结果文件夹路径：", value="./output_translations")

    # 语言选项
    LANG_OPTIONS = {
        "阿拉伯语 (Arabic)": "Arabic", "英语 (English)": "English", "西班牙语 (Spanish)": "Spanish",
        "葡萄牙语 (Portuguese)": "Portuguese", "德语 (German)": "German", "法语 (French)": "French",
        "意大利语 (Italian)": "Italian", "印尼语 (Indonesian)": "Indonesian", "印地语 (Hindi)": "Hindi",
        "泰语 (Thai)": "Thai", "马来语 (Malay)": "Malay", "日本语 (Japanese)": "Japanese",
        "韩语 (Korean)": "Korean", "中文（繁体） (Traditional Chinese)": "Traditional Chinese"
    }

    target_displays = st.multiselect("🌐 选择目标语言（可多选）", list(LANG_OPTIONS.keys()), default=["英语 (English)"])
    target_langs = [LANG_OPTIONS[d] for d in target_displays]

    translate_model = st.selectbox("🤖 翻译模型 (成本差异大，请谨慎选择)", list(MODEL_COST.keys()), index=1)
    st.markdown(f"> 当前选中模型 `{translate_model}`，请注意其 [input/output] 价格：[${MODEL_COST[translate_model]['input']}/${MODEL_COST[translate_model]['output']}] 每百万 Token。")
    
    reset = st.checkbox("🔄 强制重置所有记忆？（将删除所有 temp 文件夹下的记忆文件）", key="reset_all")
    st.markdown("---")


    if st.button("🚀 开始批量翻译", type="primary"):
        # 1. 前置检查
        if not input_dir or not os.path.exists(input_dir) or not os.path.isdir(input_dir):
            st.warning("⚠️ 请提供有效的输入文件夹路径！")
            return
        if not output_root:
            st.warning("⚠️ 请提供输出翻译结果文件夹路径！")
            return
        if not target_langs:
            st.warning("⚠️ 请选择至少一种语言！")
            return

        srt_files = sorted(
            [f for f in os.listdir(input_dir) if f.lower().endswith(".srt")],
            key=natural_sort_key
        )
        if not srt_files:
            st.warning("⚠️ 输入文件夹中没有找到 SRT 文件！")
            return

        # 2. 重置所有记忆文件
        if reset:
            st.info("🔄 正在强制重置所有记忆文件...")
            try:
                for file in TEMP_DIR.glob('memory_*.json'):
                    file.unlink()
                st.success("✅ 所有记忆文件已删除。")
            except Exception as e:
                st.error(f"❌ 删除记忆文件失败: {e}")
                return

        # 3. 并发执行
        progress_bar = st.progress(0, text="初始化中...")
        total = len(target_langs)
        done = 0
        
        max_threads = min(len(target_langs), 4) 
        st.info(f"▶️ 正在启动 {max_threads} 个线程进行并发翻译...")
        
        result_container = st.container()

        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            # 传递所有需要的参数给 process_language
            futures = {
                executor.submit(
                    process_language, 
                    lang, input_dir, output_root, srt_files, 
                    translate_model, client, TEMP_DIR
                ): lang for lang in target_langs
            }
            
            for future in as_completed(futures):
                lang = futures[future]
                try:
                    result_list = future.result()
                    with result_container:
                        for msg in result_list:
                            st.markdown(msg)
                        st.markdown("---") 
                except Exception as e:
                    st.error(f"❌ 致命错误：{lang} 线程处理出错: {e}")
                
                done += 1
                progress_bar.progress(done / total, text=f"已完成 {done}/{total} 种语言 ({lang})")

        st.balloons()
        st.success("🎉 所有语言翻译完成！请检查输出文件夹。")

if __name__ == "__main__":
    run()