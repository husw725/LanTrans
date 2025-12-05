import streamlit as st
from openai import OpenAI
import os
import json
from pathlib import Path
from dotenv import load_dotenv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
load_dotenv()

# --- UI & Cost Models ---
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
    "韩语 (Korean)": "Korean", "中文（繁体） (Traditional Chinese)": "Traditional Chinese",
    "中文（简体） (Simplified Chinese)": "Simplified Chinese" # Added Simplified Chinese
}

def estimate_cost(input_tokens, output_tokens, model):
    cost = (input_tokens / 1_000_000 * MODEL_COST[model]["input"]) + \
           (output_tokens / 1_000_000 * MODEL_COST[model]["output"])
    return cost

# --- Helper Function for Parallel Processing ---
def _process_single_language(lang_to_process, srt_files_for_lang, client_instance, temp_dir_path, input_dir_path, output_root_path, translate_model_name, memory_model_name, reset_flag):
    lang_results = [] # To store logs for this language
    lang_total_cost = 0.0
    lang_results.append(f'''--- 
### 🟢 开始处理语言: **{lang_to_process}**''')
    
    memory_path = temp_dir_path / f"drama_memory_{lang_to_process}.json"
    output_dir = Path(output_root_path) / lang_to_process
    output_dir.mkdir(parents=True, exist_ok=True)

    if reset_flag and memory_path.exists():
        memory_path.unlink()
    
    try:
        memory = json.load(open(memory_path, "r", encoding="utf-8")) if memory_path.exists() else {}
    except json.JSONDecodeError:
        memory = {}
    if not memory:
        memory = {"episode_count": 0, "characters": {}, "terminology": {}, "style_notes": ""}

    for srt_file in srt_files_for_lang:
        output_path = output_dir / srt_file
        if output_path.exists():
            lang_results.append(f"➡️ 跳过 {lang_to_process} - {srt_file}")
            continue

        try:
            with open(Path(input_dir_path) / srt_file, "r", encoding="utf-8") as f:
                srt_content = f.read()

            system_prompt = f"""You are a professional subtitle translator for short dramas, specializing in localization. Your task is to translate subtitles into {lang_to_process}.
- **Translate names into a localized form that is natural and culturally appropriate for {lang_to_process} speakers.** For example, if translating 'John' to Spanish, 'Juan' might be a good option.
- Preserve the original SRT format, including timestamps.
- Maintain the original tone and style of the dialogue.
- Use the provided memory to ensure consistency for character names and terminology.
- Do not add any translator notes or any text outside of the SRT format.

Current memory: {json.dumps(memory, ensure_ascii=False)}
"""
            user_prompt = f"Translate the following subtitles:\n{srt_content}"
            
            resp = client_instance.chat.completions.create(
                model=translate_model_name,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            )
            translated_srt = resp.choices[0].message.content.strip()
            
            cost = estimate_cost(len(system_prompt.split()) + len(user_prompt.split()), len(translated_srt.split()), translate_model_name)
            lang_total_cost += cost

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(translated_srt)
            lang_results.append(f"✅ 完成 {lang_to_process} - {srt_file} (费用: ${cost:.4f})")

            # --- Attempt to Update Memory (Safely) ---
            try:
                mem_system_prompt = "You are an assistant that updates a JSON object. ONLY output a valid, raw JSON object without explanations or markdown."
                mem_user_prompt = f"""Analyze the translated SRT and update the memory JSON.
- Identify character names and any specific terminology.
- If a name has been localized, store both the original and the localized version in the 'characters' section.
- Update the 'terminology' and 'style_notes' as needed.
- Return the complete, updated JSON object.

Previous memory: {json.dumps(memory, ensure_ascii=False)}
Translated SRT:
{translated_srt}
"""
                
                upd_resp = client_instance.chat.completions.create(
                    model=memory_model_name,
                    messages=[{"role": "system", "content": mem_system_prompt}, {"role": "user", "content": mem_user_prompt}]
                )
                response_text = upd_resp.choices[0].message.content.strip()
                
                if response_text:
                    new_memory = json.loads(response_text)
                    memory.update(new_memory)
                    json.dump(memory, open(memory_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                else:
                    lang_results.append(f"⚠️ {srt_file} 的记忆更新返回为空，本次记忆未更新。")

            except json.JSONDecodeError:
                lang_results.append(f"⚠️ {srt_file} 的记忆更新未能生成有效JSON，本次记忆未更新。")
            except Exception as mem_e:
                lang_results.append(f"⚠️ 更新 {srt_file} 的记忆时出错: {mem_e}，本次记忆未更新。")

        except Exception as e:
            lang_results.append(f"❌ {lang_to_process} - {srt_file} 翻译失败: {e}")
            continue
    
    lang_results.append(f"💰 **{lang_to_process}** 总费用: **${lang_total_cost:.4f}**")
    return lang_results, lang_total_cost


# --- Main Application ---
def run():
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except Exception as e:
        st.error(f"OpenAI API 密钥初始化失败，请检查您的 .env 文件: {e}")
        return

    TEMP_DIR = Path("./temp")
    TEMP_DIR.mkdir(exist_ok=True)

    st.header("📝 Step 1: 批量多语言翻译 SRT")
    st.caption("使用 AI 批量翻译 SRT 字幕文件，提供实时进度和成本估算。")

    # --- UI Layout ---
    with st.container(border=True):
        st.subheader("📁 路径设置")
        col1, col2 = st.columns(2)
        with col1:
            input_dir = st.text_input("SRT 输入文件夹路径：", help="存放原始 `.srt` 文件的文件夹。" )
        with col2:
            output_root = st.text_input("翻译结果输出文件夹路径：", help="翻译后的文件将按语言保存在此文件夹下。" )

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
        reset = st.checkbox("清除历史记录，重新翻译所有文件", key="reset_all", help="勾选此项将删除所有语言的翻译记忆，从头开始。" )

    st.divider()

    if st.button("🚀 开始批量翻译", type="primary", use_container_width=True):
        if not all([input_dir, output_root, target_langs]) or not os.path.exists(input_dir):
            st.warning("请确保所有路径均已正确填写，并至少选择一种目标语言。" )
            return
        
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]
            
        all_files = [f for f in os.listdir(input_dir) if f.lower().endswith(".srt")]
        srt_files = sorted(all_files, key=natural_sort_key)

        if not srt_files:
            st.warning("输入文件夹中没有找到 SRT 文件！")
            return

        # --- Concurrent Execution & Display ---
        progress_bar = st.progress(0, text="任务准备就绪...")
        log_container = st.container(height=300, border=True)
        total_langs_count = len(target_langs)
        completed_langs_count = 0
        total_cost_all_langs = 0.0

        with ThreadPoolExecutor(max_workers=min(total_langs_count, 4)) as executor:
            futures = {executor.submit(_process_single_language, lang, srt_files, client, TEMP_DIR, input_dir, output_root, translate_model, memory_model, reset): lang for lang in target_langs}
            for future in as_completed(futures):
                lang = futures[future]
                try:
                    lang_results, lang_cost = future.result()
                    for msg in lang_results:
                        if "✅" in msg:
                            log_container.success(msg)
                        elif "➡️" in msg:
                            log_container.info(msg)
                        elif "❌" in msg or "⚠️" in msg:
                            log_container.warning(msg)
                        else:
                            log_container.markdown(msg) # For markdown formatted messages
                    total_cost_all_langs += lang_cost
                except Exception as e:
                    log_container.error(f"{lang} 处理时发生严重错误: {e}")
                
                completed_langs_count += 1
                progress_bar.progress(completed_langs_count / total_langs_count, text=f"正在翻译: {completed_langs_count}/{total_langs_count} 种语言已完成")

        st.balloons()
        st.success(f"🎉 所有翻译任务完成！总预估费用: ${total_cost_all_langs:.4f}")
