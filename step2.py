import streamlit as st
import os
from pathlib import Path

import config
from translator import get_client, load_memory, save_memory, translate_srt, update_memory


def run():
    client = get_client()
    if client is None:
        st.error("未检测到 OPENAI_API_KEY，请检查项目根目录下的 .env 文件。")
        return

    st.header("🔄 Step 2: 单集重新翻译")
    st.caption("手动选择单个已翻译的 SRT 文件进行微调或重新生成，以优化翻译质量。")

    with st.container(border=True):
        st.subheader("🎯 选择目标文件")

        # 扫描 temp 下已有记忆文件
        memory_files = sorted(config.TEMP_DIR.glob("drama_memory_*.json"))
        lang_memories = {f.stem.replace("drama_memory_", ""): f for f in memory_files}
        if not lang_memories:
            st.info("尚未发现任何语言的翻译记忆，请先在 Step 1 中运行翻译。")
            return

        output_dir = st.text_input("翻译结果 SRT 所在文件夹（Step1 输出）：", help="请指向 Step 1 中设置的输出文件夹。")

        srt_file = None
        if output_dir and os.path.isdir(output_dir):
            srt_files = sorted(f for f in os.listdir(output_dir) if f.lower().endswith(".srt"))
            if srt_files:
                srt_file = st.selectbox("选择需要重新翻译的 SRT 文件：", srt_files)
            else:
                st.info("此文件夹下未找到 SRT 文件。")
        else:
            st.info("请输入有效的文件夹路径以加载 SRT 文件。")

        col1, col2 = st.columns(2)
        with col1:
            target_lang = st.selectbox("选择目标语言：", list(lang_memories.keys()),
                                       help="确保选中的语言在 Step 1 中已生成过记忆文件。")
        with col2:
            translate_model = st.selectbox("翻译模型", config.TRANSLATE_MODELS, index=0)

    st.divider()

    if st.button("🔄 开始重新翻译", type="primary", use_container_width=True) and srt_file and target_lang:
        srt_path = Path(output_dir) / srt_file
        mem_path = lang_memories.get(target_lang)
        memory = load_memory(mem_path)

        with st.spinner("翻译中，请稍候..."):
            try:
                srt_content = srt_path.read_text(encoding="utf-8")
                translated, cost = translate_srt(client, srt_content, target_lang, translate_model, memory)

                # 更新记忆（失败不影响译文）
                new_memory, mem_cost, err = update_memory(client, translated, memory, config.DEFAULT_MEMORY_MODEL)
                if new_memory is not None:
                    memory.update(new_memory)
                    save_memory(memory, mem_path)
                elif err:
                    st.warning(f"⚠️ {err}，本次未更新记忆。")

                output_path = Path(output_dir) / f"retranslated_{srt_file}"
                output_path.write_text(translated, encoding="utf-8")

                st.success(f"🎉 重新翻译完成！费用约 ${cost + mem_cost:.4f}，已保存为: `{output_path}`")
                with st.expander("查看新生成的 SRT 内容 📖"):
                    st.code(translated, language="srt")
            except Exception as e:
                st.error(f"翻译过程中发生错误: {e}")
