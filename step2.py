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

    st.header("Step 2: 单集重新生成翻译")

    # 扫描 temp 下已有记忆文件
    episode_files = sorted(TEMP_DIR.glob("episode_*.json"))
    if episode_files:
        episodes = [f.stem.split("_")[1] for f in episode_files]
    else:
        episodes = []

    episode_number = st.selectbox("选择集数", episodes)

    # 自动获取对应的 SRT 文件夹（假设输出目录统一）
    output_dir = st.text_input("翻译结果 SRT 所在文件夹（Step1 输出）", "")
    if output_dir and os.path.exists(output_dir):
        srt_files = sorted([f for f in os.listdir(output_dir) if f.lower().endswith(".srt")])
        srt_file = st.selectbox("选择需要重新翻译的 SRT 文件", srt_files)
    else:
        srt_file = None

    target_lang = st.selectbox("目标语言", ["English","Japanese","Korean","Spanish","French","German","Thai","Vietnamese"])

    if st.button("重新翻译") and srt_file and episode_number:
        srt_path = Path(output_dir)/srt_file
        memory_path = TEMP_DIR/f"episode_{episode_number}.json"

        # 加载记忆
        if memory_path.exists():
            try:
                with open(memory_path,"r",encoding="utf-8") as f:
                    memory = json.load(f)
            except Exception:
                memory = {"episode_count":int(episode_number)-1,"characters":{},"terminology":{},"style_notes":""}
        else:
            memory = {"episode_count":int(episode_number)-1,"characters":{},"terminology":{},"style_notes":""}

        with open(srt_path,"r",encoding="utf-8") as f:
            srt_content = f.read()

        system_prompt = f"""
    You are a professional subtitle translator for short dramas.
    Translate subtitles into {target_lang} while preserving SRT format, character tone, and style.
    Current memory: {memory}
    Do not add translator notes outside of SRT.
    """
        user_prompt = f"Translate the following subtitles:\n{srt_content}"

        with st.spinner("翻译中..."):
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role":"system","content":system_prompt},
                    {"role":"user","content":user_prompt}
                ]
            )
        translated_srt = response.choices[0].message.content.strip()

        # 更新记忆
        update_prompt = f"""
    Analyze the following translated SRT and update the memory for characters, terminology, and style notes.
    Previous memory: {memory}
    Translated SRT:\n{translated_srt}

    Output the updated memory in JSON format.
    """
        update_resp = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role":"system","content":"You are a memory updater for a subtitle translation system."},
                {"role":"user","content":update_prompt}
            ]
        )
        new_memory_text = update_resp.choices[0].message.content.strip()
        try:
            new_memory = json.loads(new_memory_text)
            with open(memory_path,"w",encoding="utf-8") as f:
                json.dump(new_memory,f,ensure_ascii=False,indent=2)
        except Exception:
            st.warning("⚠️ 无法解析更新后的 memory, 保持原 memory")

        output_path = Path(output_dir)/f"retranslated_{srt_file}"
        with open(output_path,"w",encoding="utf-8") as f:
            f.write(translated_srt)

        st.success(f"重新翻译完成，保存为: {output_path}")