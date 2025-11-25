import streamlit as st
from moviepy.editor import VideoFileClip
from pathlib import Path
import os

def batch_video_compress():
    st.header("🗜️ Step 4: 批量压缩视频")
    st.caption("使用 H.264 (libx264) 编码器高效压缩视频，减小文件体积，方便存储和分享。")

    # --- UI Layout ---
    with st.container(border=True):
        st.subheader("📁 路径设置")
        col1, col2 = st.columns(2)
        with col1:
            input_dir = st.text_input("输入视频文件夹路径", help="包含您想要压缩的视频文件的文件夹。")
        with col2:
            output_dir = st.text_input("输出视频文件夹路径", help="压缩后的视频将保存到这里。")

    with st.container(border=True):
        st.subheader("⚙️ 压缩设置")
        
        selected_crf = st.select_slider(
            "压缩质量 (CRF 值)",
            options=[16, 18, 20, 22, 24, 26, 28, 30],
            value=22,
            help="**CRF (Constant Rate Factor)** 是衡量视频质量的关键参数。值越低，质量越高，文件越大。推荐范围 18-28。"
        )
        st.info(f"当前选择 **CRF {selected_crf}**: {'高质量' if selected_crf < 20 else '均衡' if selected_crf < 25 else '小体积'}")
        
        overwrite = st.checkbox("覆盖已存在的输出文件", value=False)
    
    st.divider()

    # --- Execution Logic ---
    if st.button("🚀 开始压缩视频", type="primary", use_container_width=True):
        if not input_dir or not os.path.exists(input_dir):
            st.warning("❗ 请输入有效的输入文件夹路径")
            return
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        video_files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith((".mp4", ".mov", ".mkv"))])
        if not video_files:
            st.warning("❗ 输入文件夹内没有找到视频文件")
            return

        total = len(video_files)
        progress_bar = st.progress(0, text="任务准备就绪...")
        log_container = st.container(height=400, border=True)

        for i, video_name in enumerate(video_files):
            in_path = os.path.join(input_dir, video_name)
            out_path = os.path.join(output_dir, video_name)
            
            progress_text = f"进度: {i + 1}/{total} | 正在压缩: {video_name}"
            progress_bar.progress((i + 1) / total, text=progress_text)

            if os.path.exists(out_path) and not overwrite:
                log_container.info(f"➡️ {video_name} 已存在，跳过")
                continue

            log_container.write(f"🎬 开始压缩: {video_name} (CRF={selected_crf})")
            
            try:
                with VideoFileClip(in_path) as clip:
                    clip.write_videofile(
                        out_path,
                        codec="libx264",
                        audio_codec="aac",
                        preset="slow",
                        ffmpeg_params=["-crf", str(selected_crf), "-pix_fmt", "yuv420p"],
                        threads=4,
                        logger=None
                    )
                log_container.success(f"✅ 压缩完成: {video_name}")
            except Exception as e:
                log_container.error(f"❌ 压缩 {video_name} 时出错: {e}")

        st.balloons()
        st.success("🎉 所有视频压缩完成！")

if __name__ == "__main__":
    batch_video_compress()