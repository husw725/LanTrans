import streamlit as st
from openai import OpenAI
from key import key as API_KEY
import os
import json
from pathlib import Path

def run():
    client = OpenAI(api_key=API_KEY)
    TEMP_DIR = Path("./temp")
    TEMP_DIR.mkdir(exist_ok=True)

    st.header("🔄 Step 2: 单集重新翻译")
    st.caption("手动选择单个已翻译的 SRT 文件进行微调或重新生成，以优化翻译质量。")

    with st.container(border=True):
        st.subheader("🎯 选择目标文件")

        # 扫描 temp 下已有记忆文件
        memory_files = sorted(TEMP_DIR.glob("drama_memory_*.json"))
        lang_memories = {f.stem.replace("drama_memory_", ""): f for f in memory_files}
        
        output_dir = st.text_input("翻译结果 SRT 所在文件夹（Step1 输出）：", help="请指向 Step 1 中设置的输出文件夹。")

        # 动态加载 SRT 文件
        if output_dir and os.path.exists(output_dir):
            srt_files = sorted([f for f in os.listdir(output_dir) if f.lower().endswith(".srt")])
            if not srt_files:
                st.info("此文件夹下未找到 SRT 文件。")
                srt_file = None
            else:
                srt_file = st.selectbox("选择需要重新翻译的 SRT 文件：", srt_files)
        else:
            srt_file = None
            st.info("请输入有效的文件夹路径以加载 SRT 文件。")

        col1, col2 = st.columns(2)
        with col1:
            # 假设记忆文件与语言文件夹同名
            target_lang = st.selectbox("选择目标语言：", list(lang_memories.keys()), help="确保选中的语言在 Step 1 中已生成过记忆文件。")
        
        # Note: 'episode_number' seems less relevant than the language-specific memory file from step 1.
        # Refactoring to use the more robust language-based memory.
        # If episode-specific memory is needed, the logic would need significant changes.
        # For now, aligning with step 1's memory structure.
    
    st.divider()

    if st.button("🔄 开始重新翻译", type="primary", use_container_width=True) and srt_file and target_lang:
        srt_path = Path(output_dir) / srt_file
        memory_path = lang_memories.get(target_lang)

        if not memory_path or not memory_path.exists():
            st.error(f"未能找到 {target_lang} 的记忆文件，无法进行翻译。请先在 Step 1 中运行该语言的翻译任务。")
            return

        # 加载记忆
        try:
            with open(memory_path, "r", encoding="utf-8") as f:
                memory = json.load(f)
        except Exception as e:
            st.error(f"加载记忆文件失败: {e}")
            memory = {"episode_count": 0, "characters": {}, "terminology": {}, "style_notes": ""}

        with open(srt_path, "r", encoding="utf-8") as f:
            srt_content = f.read()

        system_prompt = f"You are a professional subtitle translator for short dramas. Translate subtitles into {target_lang} while preserving SRT format, character tone, and style. Current memory: {memory}. Do not add translator notes outside of SRT."
        user_prompt = f"Translate the following subtitles:\n{srt_content}"

        with st.spinner("翻译中，请稍候..."):
            try:
                response = client.chat.completions.create(
                    model="gpt-5.1",  # Using a consistent, high-quality model
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                translated_srt = response.choices[0].message.content.strip()

                # 更新记忆
                update_prompt = f"Analyze the following translated SRT and update the memory... Previous memory: {memory} Translated SRT:\n{translated_srt} Output updated memory in JSON."
                update_resp = client.chat.completions.create(
                    model="gpt-5-mini", # Use a faster model for memory updates
                    messages=[
                        {"role": "system", "content": "You are a memory updater for a subtitle translation system."},
                        {"role": "user", "content": update_prompt}
                    ]
                )
                new_memory = json.loads(update_resp.choices[0].message.content.strip())
                memory.update(new_memory)
                with open(memory_path, "w", encoding="utf-8") as f:
                    json.dump(memory, f, ensure_ascii=False, indent=2)
                
                output_path = Path(output_dir) / f"retranslated_{srt_file}"
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(translated_srt)

                st.success(f"🎉 重新翻译完成！已保存为: `{output_path}`")
                
                with st.expander("查看新生成的 SRT 内容 📖"):
                    st.code(translated_srt, language="srt")

            except Exception as e:
                st.error(f"翻译过程中发生错误: {e}")