import streamlit as st
from openai import OpenAI
# from key import key as API_KEY
import os
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
load_dotenv()

# --- UI & Cost Models ---

# 模型费用表 (保持不变)
MODEL_COST = {
    "gpt-5.1": {"input": 1.25, "output": 10.0},
    "gpt-5": {"input": 1.25, "output": 10.0},
    "gpt-5-mini": {"input": 0.25, "output": 2.0},
    "gpt-5-nano": {"input": 0.05, "output": 0.4},
}

LANG_OPTIONS = {
    "阿拉伯语 (Arabic)": "Arabic", "英语 (English)": "English", "西班牙语 (Spanish)": "Spanish",
    "葡萄牙语 (Portuguese)": "Portuguese", "德语 (German)": "German", "法语 (French)": "French",
    "意大利语 (Italian)": "Italian", "印尼语 (Indonesian)": "Indonesian", "印地语 (Hindi)": "Hindi",
    "泰语 (Thai)": "Thai", "马来语 (Malay)": "Malay", "日本语 (Japanese)": "Japanese",
    "韩语 (Korean)": "Korean", "中文（繁体） (Traditional Chinese)": "Traditional Chinese"
}

def estimate_cost(input_tokens, output_tokens, model):
    cost = (input_tokens / 1_000_000 * MODEL_COST[model]["input"]) + \
           (output_tokens / 1_000_000 * MODEL_COST[model]["output"])
    return cost

# --- Main Application ---
def run():
    client = OpenAI()
    TEMP_DIR = Path("./temp")
    TEMP_DIR.mkdir(exist_ok=True)

    st.header("📝 Step 1: 批量多语言翻译 SRT")
    st.caption("使用 AI 批量翻译 SRT 字幕文件，支持多语言并发处理和成本估算。")

    # --- UI Layout ---
    with st.container(border=True):
        st.subheader("📁 路径设置")
        col1, col2 = st.columns(2)
        with col1:
            input_dir = st.text_input("SRT 输入文件夹路径：", help="存放原始 `.srt` 文件的文件夹。")
        with col2:
            output_root = st.text_input("翻译结果输出文件夹路径：", help="翻译后的文件将按语言保存在此文件夹下。")

    with st.container(border=True):
        st.subheader("⚙️ 翻译设置")
        target_displays = st.multiselect("选择目标语言（可多选）", list(LANG_OPTIONS.keys()))
        target_langs = [LANG_OPTIONS[d] for d in target_displays]

        m_col1, m_col2 = st.columns(2)
        with m_col1:
            translate_model = st.selectbox("翻译模型", ["gpt-5.1", "gpt-5-mini", "gpt-5-nano"], index=0)
        with m_col2:
            memory_model = st.selectbox("Memory 更新模型", ["gpt-5.1", "gpt-5-mini", "gpt-5-nano"], index=0)

    with st.expander("高级选项"):
        reset = st.checkbox("清除历史记录，重新翻译所有文件", key="reset_all", help="勾选此项将删除所有语言的翻译记忆，从头开始。")

    st.divider()

    if st.button("🚀 开始批量翻译", type="primary", use_container_width=True):
        # --- Input Validation ---
        if not input_dir or not os.path.exists(input_dir):
            st.warning("请提供有效的输入文件夹路径！")
            return
        if not output_root:
            st.warning("请提供输出文件夹路径！")
            return
        if not target_langs:
            st.warning("请选择至少一种语言！")
            return

        srt_files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith(".srt")])
        if not srt_files:
            st.warning("输入文件夹中没有找到 SRT 文件！")
            return

        # --- Processing Logic ---
        def process_language(lang):
            # (处理逻辑与原版相同)
            memory_path = TEMP_DIR / f"drama_memory_{lang}.json"
            output_dir = Path(output_root) / lang
            output_dir.mkdir(parents=True, exist_ok=True)

            if reset and memory_path.exists():
                memory_path.unlink()
            
            try:
                memory = json.load(open(memory_path, "r", encoding="utf-8")) if memory_path.exists() else {}
            except json.JSONDecodeError:
                memory = {}
            
            if not memory:
                 memory = {"episode_count": 0, "characters": {}, "terminology": {}, "style_notes": ""}


            results = []
            total_cost = 0.0

            for srt_file in srt_files:
                output_path = output_dir / srt_file
                if output_path.exists():
                    results.append(f"➡️ 跳过 {lang} - {srt_file}")
                    continue

                with open(Path(input_dir) / srt_file, "r", encoding="utf-8") as f:
                    srt_content = f.read()

                system_prompt = f"You are a professional subtitle translator for short dramas. Translate subtitles into {lang} while preserving SRT format, tone, and style. Current memory: {memory}. Do not add any translator notes outside of SRT."
                user_prompt = f"Translate the following subtitles:\n{srt_content}"

                try:
                    resp = client.chat.completions.create(
                        model=translate_model,
                        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
                    )
                    translated_srt = resp.choices[0].message.content.strip()
                    input_tokens = len(system_prompt.split()) + len(user_prompt.split())
                    output_tokens = len(translated_srt.split())
                    cost = estimate_cost(input_tokens, output_tokens, translate_model)
                    total_cost += cost

                    update_prompt = f"Analyze the following translated SRT and update the memory for characters, terminology, and style notes. Previous memory: {memory}. Translated SRT:\n{translated_srt}. Output the updated memory in JSON format."
                    upd_resp = client.chat.completions.create(
                        model=memory_model,
                        messages=[{"role": "system", "content": "You are a memory updater..."}, {"role": "user", "content": update_prompt}]
                    )
                    new_memory = json.loads(upd_resp.choices[0].message.content.strip())
                    memory.update(new_memory)
                    json.dump(memory, open(memory_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(translated_srt)
                    results.append(f"✅ 完成 {lang} - {srt_file}, 费用 ${cost:.4f}")

                except Exception as e:
                    results.append(f"❌ {lang} - {srt_file} 翻译失败: {e}")
                    continue
            
            results.append(f"💰 {lang} 总费用: ${total_cost:.4f}")
            return results

        # --- Concurrent Execution & Display ---
        progress_bar = st.progress(0, text="任务准备就绪...")
        log_container = st.container(height=300, border=True)
        total_tasks = len(target_langs)
        completed_tasks = 0

        with ThreadPoolExecutor(max_workers=min(total_tasks, 4)) as executor:
            futures = {executor.submit(process_language, lang): lang for lang in target_langs}
            for future in as_completed(futures):
                lang = futures[future]
                try:
                    result_list = future.result()
                    for msg in result_list:
                        if "✅" in msg:
                            log_container.success(msg)
                        elif "➡️" in msg:
                             log_container.info(msg)
                        elif "❌" in msg or "⚠️" in msg:
                            log_container.warning(msg)
                        else:
                            log_container.write(msg)
                except Exception as e:
                    log_container.error(f"{lang} 处理时发生严重错误: {e}")
                
                completed_tasks += 1
                progress_bar.progress(completed_tasks / total_tasks, text=f"正在翻译: {completed_tasks}/{total_tasks} 种语言已完成")

        st.balloons()
        st.success("🎉 所有语言翻译完成！")