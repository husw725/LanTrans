import streamlit as st
import os
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from translator import get_client, load_memory, save_memory, translate_srt, update_memory, trim_memory
from ui_utils import validate_dir


def _natural_sort_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'([0-9]+)', s)]


def _process_single_language(lang, srt_files, client, input_dir, output_root, translate_model, memory_model, reset):
    """翻译某一种语言的所有 SRT，返回 (日志列表, 该语言总费用)。在工作线程中运行。"""
    logs = [f"### 🟢 开始处理语言: **{lang}**"]
    lang_cost = 0.0

    mem_path = config.memory_path(lang)
    output_dir = Path(output_root) / lang
    output_dir.mkdir(parents=True, exist_ok=True)

    if reset and mem_path.exists():
        mem_path.unlink()
    memory = load_memory(mem_path)

    for srt_file in srt_files:
        output_path = output_dir / srt_file
        if output_path.exists():
            logs.append(f"➡️ 跳过 {lang} - {srt_file}")
            continue
        try:
            srt_content = (Path(input_dir) / srt_file).read_text(encoding="utf-8")
            translated, cost = translate_srt(client, srt_content, lang, translate_model, memory)
            lang_cost += cost
            output_path.write_text(translated, encoding="utf-8")
            logs.append(f"✅ 完成 {lang} - {srt_file} (费用: ${cost:.4f})")

            # 更新记忆（失败不影响译文）
            new_memory, mem_cost, err = update_memory(client, translated, memory, memory_model)
            lang_cost += mem_cost
            if new_memory is not None:
                memory.update(new_memory)
                trim_memory(memory)
                save_memory(memory, mem_path)
            elif err:
                logs.append(f"⚠️ {srt_file}: {err}，本次记忆未更新。")
        except Exception as e:
            logs.append(f"❌ {lang} - {srt_file} 翻译失败: {e}")
            continue

    logs.append(f"💰 **{lang}** 总费用: **${lang_cost:.4f}**")
    return logs, lang_cost


def run():
    client = get_client()
    if client is None:
        st.error("未检测到 OPENAI_API_KEY，请检查项目根目录下的 .env 文件。")
        return

    with st.container(border=True):
        st.subheader("📁 路径设置")
        col1, col2 = st.columns(2)
        with col1:
            input_dir = st.text_input("SRT 输入文件夹路径：", help="存放原始 `.srt` 文件的文件夹。")
            srt_files = validate_dir(input_dir, exts=(".srt",))
        with col2:
            output_root = st.text_input("翻译结果输出文件夹路径：", help="翻译后的文件将按语言保存在此文件夹下。")
            if output_root:
                st.caption(f"将创建子文件夹：`{output_root}/<语言>/`")

    with st.container(border=True):
        st.subheader("⚙️ 翻译设置")
        target_displays = st.multiselect("选择目标语言（可多选）", list(config.LANG_OPTIONS.keys()))
        target_langs = [config.LANG_OPTIONS[d] for d in target_displays]
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            translate_model = st.selectbox("翻译模型", config.TRANSLATE_MODELS, index=0,
                                           help="默认 gpt-5.4-mini：比旧款更便宜且质量更好。")
        with m_col2:
            memory_model = st.selectbox("Memory 更新模型", config.MEMORY_MODELS, index=0,
                                        help="只输出 JSON，用最便宜的 nano 即可。")

    with st.expander("高级选项"):
        reset = st.checkbox("清除历史记录，重新翻译所有文件", key="reset_all",
                            help="勾选将删除所选语言的翻译记忆，从头开始。")
        reset_confirmed = True
        if reset:
            st.warning("⚠️ 此操作会删除所选语言已有的翻译记忆，且无法恢复。")
            reset_confirmed = st.checkbox("我已了解，确认清除记忆", key="reset_confirm")

    st.divider()

    if st.button("🚀 开始批量翻译", type="primary", use_container_width=True):
        if not (input_dir and output_root and target_langs) or not os.path.isdir(input_dir):
            st.warning("请确保所有路径均已正确填写，并至少选择一种目标语言。")
            return
        if reset and not reset_confirmed:
            st.warning("你勾选了「清除历史记录」，请先勾选确认框再开始。")
            return
        if not srt_files:
            st.warning("输入文件夹中没有找到 SRT 文件！")
            return

        srt_files = sorted(srt_files, key=_natural_sort_key)
        total = len(target_langs)
        progress = st.progress(0, text="任务准备就绪...")
        # 每种语言一个独立折叠状态块，互不干扰
        status_blocks = {lang: st.status(f"⏳ 等待中：{lang}", state="running") for lang in target_langs}
        done, total_cost = 0, 0.0

        with ThreadPoolExecutor(max_workers=min(total, 4)) as executor:
            futures = {executor.submit(_process_single_language, lang, srt_files, client, input_dir,
                                       output_root, translate_model, memory_model, reset): lang
                       for lang in target_langs}
            for future in as_completed(futures):
                lang = futures[future]
                block = status_blocks[lang]
                try:
                    logs, cost = future.result()
                    total_cost += cost
                    for msg in logs:
                        block.markdown(msg)
                    block.update(label=f"✅ 完成：{lang}（${cost:.4f}）", state="complete")
                except Exception as e:
                    block.markdown(f"严重错误: {e}")
                    block.update(label=f"❌ 失败：{lang}", state="error")
                done += 1
                progress.progress(done / total, text=f"已完成 {done}/{total} 种语言")

        st.balloons()
        st.success(f"🎉 所有翻译任务完成！总预估费用: ${total_cost:.4f}")
