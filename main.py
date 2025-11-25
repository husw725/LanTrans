import streamlit as st

# --- Page Configuration ---
st.set_page_config(
    page_title="LanTrans 视频翻译工具",
    page_icon="🎬",
    layout="wide"
)

# --- Sidebar Navigation ---
with st.sidebar:
    st.image("https://img.icons8.com/nolan/64/movie-projector.png", width=60)
    st.title("LanTrans 工具箱")
    
    st.info("小提示：点击右上角菜单 > Settings 即可切换浅色/深色主题。")

    step = st.radio(
        "选择功能",
        [
            "📝 Step 1: 批量翻译 SRT",
            "🔄 Step 2: 单集重新翻译",
            "🎨 Step 3: 批量添加字幕",
            "🗜️ Step 4: 批量压缩视频"
        ],
        help="请选择您需要使用的功能模块"
    )

st.header("🎬 LanTrans 视频翻译流程")
st.markdown("---")


if "Step 1" in step:
    from step1 import run
    run()
elif "Step 2" in step:
    from step2 import run
    run()
elif "Step 3" in step:
    from step3 import run
    run()
elif "Step 4" in step:
    from step4 import batch_video_compress
    batch_video_compress()