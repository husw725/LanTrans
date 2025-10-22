import streamlit as st
from openai import OpenAI
from key import key as API_KEY
import os
import json
from pathlib import Path

client = OpenAI(api_key=API_KEY)

TEMP_DIR = Path("./temp")
TEMP_DIR.mkdir(exist_ok=True)

st.header("Step 1: 批量翻译 SRT")

# 选择是否重新开始
reset = st.checkbox("重新开始一部新剧集？")
if reset:
    for f in TEMP_DIR.glob("*.json"):
        f.unlink()
    st.session_state.drama_memory = {
        "episode_count": 0,
        "characters": {},
        "terminology": {},
        "style_notes": ""
    }

# 初始化记忆
if "drama_memory" not in st.session_state:
    episode_files = sorted(TEMP_DIR.glob("episode_*.json"))
    if episode_files:
        try:
            with open(episode_files[-1], "r", encoding="utf-8") as f:
                st.session_state.drama_memory = json.load(f)
        except Exception:
            st.session_state.drama_memory = {"episode_count":0,"characters":{},"terminology":{},"style_notes":""}
    else:
        st.session_state.drama_memory = {"episode_count":0,"characters":{},"terminology":{},"style_notes":""}

# 输入输出目录
input_dir = st.text_input("输入 SRT 文件夹路径：")
output_dir = st.text_input("输出翻译结果文件夹路径：")
target_lang = st.selectbox("目标语言", ["English","Japanese","Korean","Spanish","French","German","Thai","Vietnamese"])

if st.button("开始批量翻译"):
    if not input_dir or not os.path.exists(input_dir):
        st.warning("请提供有效的输入文件夹路径！")
    elif not output_dir:
        st.warning("请提供输出文件夹路径！")
    else:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        srt_files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith(".srt")])
        if not srt_files:
            st.warning("输入文件夹中没有找到 SRT 文件！")
        else:
            for idx, srt_file in enumerate(srt_files, start=1):
                input_path = os.path.join(input_dir, srt_file)
                output_path = os.path.join(output_dir, srt_file)
                memory_path = TEMP_DIR / f"episode_{idx}.json"

                if os.path.exists(output_path):
                    st.info(f"跳过已存在的文件: {srt_file}")
                    continue

                with open(input_path,"r",encoding="utf-8") as f:
                    srt_content = f.read()

                memory = st.session_state.drama_memory
                system_prompt = f"""
You are a professional subtitle translator for short dramas.
Translate subtitles into {target_lang} while preserving SRT format, character tone, and style.
Current memory: {memory}
Do not add translator notes outside of SRT.
"""
                user_prompt = f"Translate the following subtitles:\n{srt_content}"

                with st.spinner(f"翻译中: {srt_file} ..."):
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
                    st.session_state.drama_memory = new_memory
                    with open(memory_path,"w",encoding="utf-8") as f:
                        json.dump(new_memory,f,ensure_ascii=False,indent=2)
                except Exception:
                    st.warning(f"⚠️ 无法解析更新后的 memory for {srt_file}, 保持原 memory")

                # 写入输出文件
                with open(output_path,"w",encoding="utf-8") as f:
                    f.write(translated_srt)

                st.success(f"完成翻译: {srt_file}")
                st.session_state.drama_memory["episode_count"] = idx

            st.info(f"批量翻译完成！输出文件夹: {output_dir}")