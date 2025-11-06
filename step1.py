import streamlit as st
from openai import OpenAI
from key import key as API_KEY
import os
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# 模型费用表
MODEL_COST = {
    "gpt-5": {"input": 1.25, "output": 10.0},       # $/1M tokens
    "gpt-5-mini": {"input": 0.25, "output": 2.0},
    "gpt-5-nano": {"input": 0.05, "output": 0.4},
    # "gpt-5-pro": {"input": 15.0, "output": 120.0}
}

def estimate_cost(input_tokens, output_tokens, model):
    cost = (input_tokens / 1_000_000 * MODEL_COST[model]["input"]) + \
           (output_tokens / 1_000_000 * MODEL_COST[model]["output"])
    return cost

def run():
    client = OpenAI(api_key=API_KEY)
    TEMP_DIR = Path("./temp")
    TEMP_DIR.mkdir(exist_ok=True)

    st.header("Step 1: 批量多语言翻译 SRT（支持成本估算）")

    # 输入输出目录
    input_dir = st.text_input("输入 SRT 文件夹路径：")
    output_root = st.text_input("输出翻译结果文件夹路径：")

    LANG_OPTIONS = {
        "阿拉伯语 (Arabic)": "Arabic",
        "英语 (English)": "English",
        "西班牙语 (Spanish)": "Spanish",
        "葡萄牙语 (Portuguese)": "Portuguese",
        "德语 (German)": "German",
        "法语 (French)": "French",
        "意大利语 (Italian)": "Italian",
        "印尼语 (Indonesian)": "Indonesian",
        "印地语 (Hindi)": "Hindi",
        "泰语 (Thai)": "Thai",
        "马来语 (Malay)": "Malay",
        "日本语 (Japanese)": "Japanese",
        "韩语 (Korean)": "Korean",
        "中文（繁体） (Traditional Chinese)": "Traditional Chinese"
    }

    target_displays = st.multiselect("选择目标语言（可多选）", list(LANG_OPTIONS.keys()))
    target_langs = [LANG_OPTIONS[d] for d in target_displays]

    # 模型选择
    translate_model = st.selectbox("翻译模型", [ "gpt-5","gpt-5-mini", "gpt-5-nano"], index=0)
    memory_model = st.selectbox("Memory 更新模型", [ "gpt-5","gpt-5-mini", "gpt-5-nano",], index=0)

    reset = st.checkbox("重新开始所有语言的翻译？", key="reset_all")

    if st.button("开始批量翻译"):
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

        # 每语言翻译任务
        def process_language(lang):
            memory_path = TEMP_DIR / f"drama_memory_{lang}.json"
            output_dir = Path(output_root) / lang
            output_dir.mkdir(parents=True, exist_ok=True)

            # 初始化或重置记忆
            if reset and memory_path.exists():
                memory_path.unlink()
            if memory_path.exists():
                try:
                    memory = json.load(open(memory_path, "r", encoding="utf-8"))
                except:
                    memory = {"episode_count": 0, "characters": {}, "terminology": {}, "style_notes": ""}
            else:
                memory = {"episode_count": 0, "characters": {}, "terminology": {}, "style_notes": ""}

            results = []
            total_cost = 0.0

            for idx, srt_file in enumerate(srt_files, start=1):
                input_path = os.path.join(input_dir, srt_file)
                output_path = output_dir / srt_file
                if output_path.exists():
                    results.append(f"跳过 {lang} - {srt_file}")
                    continue

                with open(input_path, "r", encoding="utf-8") as f:
                    srt_content = f.read()

                # 翻译请求
                system_prompt = f"""
                You are a professional subtitle translator for short dramas.
                Translate subtitles into {lang} while preserving SRT format, tone, and style.
                Current memory: {memory}
                Do not add any translator notes outside of SRT.
                """
                user_prompt = f"Translate the following subtitles:\n{srt_content}"

                for _ in range(3):
                    try:
                        resp = client.chat.completions.create(
                            model=translate_model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt}
                            ]
                        )
                        translated_srt = resp.choices[0].message.content.strip()
                        input_tokens = len(system_prompt.split()) + len(user_prompt.split())
                        output_tokens = len(translated_srt.split())
                        cost = estimate_cost(input_tokens, output_tokens, translate_model)
                        total_cost += cost
                        break
                    except Exception:
                        time.sleep(2)
                else:
                    results.append(f"{lang} - {srt_file} 翻译失败")
                    continue

                # 更新 memory
                update_prompt = f"""
                Analyze the following translated SRT and update the memory for characters, terminology, and style notes.
                Previous memory: {memory}
                Translated SRT:\n{translated_srt}
                Output the updated memory in JSON format.
                """
                try:
                    upd_resp = client.chat.completions.create(
                        model=memory_model,
                        messages=[
                            {"role": "system", "content": "You are a memory updater for a subtitle translation system."},
                            {"role": "user", "content": update_prompt}
                        ]
                    )
                    new_memory = json.loads(upd_resp.choices[0].message.content.strip())
                    memory.update(new_memory)
                    json.dump(memory, open(memory_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                    mem_tokens = len(update_prompt.split()) + len(json.dumps(new_memory).split())
                    total_cost += estimate_cost(mem_tokens, 0, memory_model)
                except Exception:
                    results.append(f"⚠️ {lang} - {srt_file} memory 更新失败")

                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(translated_srt)
                results.append(f"✅ 完成 {lang} - {srt_file}, 费用 ${total_cost:.4f}")

            results.append(f"💰 {lang} 总费用: ${total_cost:.4f}")
            return results

        # 多语言并发
        progress = st.progress(0)
        total = len(target_langs)
        done = 0

        with ThreadPoolExecutor(max_workers=min(len(target_langs), 4)) as executor:
            futures = {executor.submit(process_language, lang): lang for lang in target_langs}
            for future in as_completed(futures):
                lang = futures[future]
                try:
                    result_list = future.result()
                    for msg in result_list:
                        st.write(msg)
                except Exception as e:
                    st.error(f"{lang} 处理出错: {e}")
                done += 1
                progress.progress(done / total)

        st.success("✅ 所有语言翻译完成！")