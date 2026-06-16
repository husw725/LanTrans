import streamlit as st

import theme

# --- Page Configuration ---
st.set_page_config(
    page_title="LanTrans 视频翻译工具",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

theme.inject_css()

# --- 导航状态 ---
if "active_step" not in st.session_state:
    st.session_state.active_step = "step1"

# --- 顶部品牌栏 + 步骤进度条 ---
theme.render_header()
selected = theme.render_stepper(st.session_state.active_step)
if selected != st.session_state.active_step:
    st.session_state.active_step = selected
    st.rerun()

# --- 侧边栏（帮助 / 提示，折叠态） ---
with st.sidebar:
    st.markdown("### 🎬 LanTrans 工具箱")
    st.caption("一套完整的视频多语言翻译与字幕处理流程。")
    st.info("小提示：点击右上角菜单 > Settings 可切换浅色 / 深色主题。")
    st.caption("流程：① 翻译 → ② 微调 → ③ 字幕 → ④ 压缩")

# --- 路由 ---
step = st.session_state.active_step
theme.page_header(step)

if step == "step1":
    from step1 import run
    run()
elif step == "step2":
    from step2 import run
    run()
elif step == "step3":
    from step3 import run
    run()
elif step == "step4":
    from step4 import batch_video_compress
    batch_video_compress()
