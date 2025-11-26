import streamlit as st
from openai import OpenAI
import os
import json
from pathlib import Path
from dotenv import load_dotenv
import re
from concurrent.futures import ThreadPoolExecutor
import queue
import time
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
    "中文（简体） (Simplified Chinese)": "Simplified Chinese"
}

def estimate_cost(input_tokens, output_tokens, model):
    cost = (input_tokens / 1_000_000 * MODEL_COST[model]["input"]) + \
           (output_tokens / 1_000_000 * MODEL_COST[model]["output"])
    return cost

# --- Helper Function for Parallel Processing with Queue ---
def _process_single_language_with_queue(progress_queue, lang, srt_files, client, temp_dir, input_dir, output_root, translate_model, memory_model, reset):
    lang_total_cost = 0.0
    progress_queue.put({'type': 'log', 'status': 'markdown', 'message': f"--- \n### 🟢 开始处理语言: **{lang}**"})
    
    memory_path = temp_dir / f"drama_memory_{lang}.json"
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

    for srt_file in srt_files:
        output_path = output_dir / srt_file
        if output_path.exists():
            progress_queue.put({'type': 'log', 'status': 'info', 'message': f"➡️ 跳过 {lang} - {srt_file}"})
            progress_queue.put({'type': 'progress'}) # Still count as progress
            continue

        try:
            with open(Path(input_dir) / srt_file, "r", encoding="utf-8") as f:
                srt_content = f.read()

            system_prompt = f"You are a professional subtitle translator... Current memory: {json.dumps(memory, ensure_ascii=False)}..."
            user_prompt = f"Translate the following subtitles into {lang}:\n{srt_content}"
            
            resp = client.chat.completions.create(model=translate_model, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}])
            translated_srt = resp.choices[0].message.content.strip()
            
            cost = estimate_cost(len(system_prompt.split()) + len(user_prompt.split()), len(translated_srt.split()), translate_model)
            lang_total_cost += cost

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(translated_srt)
            progress_queue.put({'type': 'log', 'status': 'success', 'message': f"✅ 完成 {lang} - {srt_file} (费用: ${cost:.4f})")

            # Attempt to Update Memory
            try:
                mem_system_prompt = "You are an assistant that updates a JSON object. ONLY output a valid, raw JSON object..."
                mem_user_prompt = f"Analyze... Previous memory: {json.dumps(memory, ensure_ascii=False)}. Translated SRT:\n{translated_srt}. Return updated JSON."
                
                upd_resp = client.chat.completions.create(model=memory_model, messages=[{"role": "system", "content": mem_system_prompt}, {"role": "user", "content": mem_user_prompt}])
                response_text = upd_resp.choices[0].message.content.strip()
                
                if response_text:
                    new_memory = json.loads(response_text)
                    memory.update(new_memory)
                    json.dump(memory, open(memory_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                else:
                    progress_queue.put({'type': 'log', 'status': 'warning', 'message': f"⚠️ {srt_file} 的记忆更新返回为空。"})
            except Exception as mem_e:
                progress_queue.put({'type': 'log', 'status': 'warning', 'message': f"⚠️ 更新 {srt_file} 的记忆时出错: {mem_e}"})

        except Exception as e:
            progress_queue.put({'type': 'log', 'status': 'error', 'message': f"❌ {lang} - {srt_file} 翻译失败: {e}"})
        
        finally:
            progress_queue.put({'type': 'progress'}) # Signal progress regardless of outcome

    progress_queue.put({'type': 'log', 'status': 'markdown', 'message': f"💰 **{lang}** 总费用: **${lang_total_cost:.4f}**"})
    progress_queue.put({'type': 'done', 'cost': lang_total_cost})


# --- Main Application ---
def run():
    # ... (UI and client setup code remains the same) ...
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

        # --- Concurrent Execution with Real-time Updates via Queue ---
        progress_queue = queue.Queue()
        total_files_to_process = len(srt_files) * len(target_langs)
        completed_files = 0
        
        progress_bar = st.progress(0, text="任务准备就绪...")
        log_container = st.container(height=300, border=True)
        
        total_langs_to_process = len(target_langs)
        completed_langs = 0
        total_cost_all_langs = 0.0

        with ThreadPoolExecutor(max_workers=min(total_langs_to_process, 4)) as executor:
            for lang in target_langs:
                executor.submit(_process_single_language_with_queue, progress_queue, lang, srt_files, client, TEMP_DIR, input_dir, output_root, translate_model, memory_model, reset)

            while completed_langs < total_langs_to_process:
                try:
                    msg = progress_queue.get(timeout=1.0) # Wait for a message

                    if msg['type'] == 'log':
                        status = msg.get('status', 'info')
                        if status == 'success': log_container.success(msg['message'])
                        elif status == 'info': log_container.info(msg['message'])
                        elif status == 'warning': log_container.warning(msg['message'])
                        elif status == 'error': log_container.error(msg['message'])
                        elif status == 'markdown': log_container.markdown(msg['message'])
                    
                    elif msg['type'] == 'progress':
                        completed_files += 1
                        progress_text = f"总进度: {completed_files}/{total_files_to_process} 文件已处理"
                        progress_bar.progress(completed_files / total_files_to_process, text=progress_text)
                    
                    elif msg['type'] == 'done':
                        completed_langs += 1
                        total_cost_all_langs += msg.get('cost', 0)
                        
                except queue.Empty:
                    # If queue is empty for a while, it might mean tasks are done or stalled
                    pass
        
        st.balloons()
        st.success(f'''🎉 所有翻译任务完成！总预估费用: ${total_cost_all_langs:.4f}'''))