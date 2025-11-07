import streamlit as st
from moviepy.editor import VideoFileClip
from pathlib import Path
import os

def batch_video_compress():
    st.header("🎞️ 视频批量压缩工具")
    st.markdown("选择输入文件夹、输出文件夹，并根据需要调整压缩质量。")

    # 输入与输出目录
    input_dir = st.text_input("📂 输入视频文件夹路径")
    output_dir = st.text_input("💾 输出视频文件夹路径")

    # CRF 档位选择（越小质量越高，文件越大）
    st.markdown("### 🎚️ 压缩质量设置")
    crf_options = {
        "无损近似（CRF 16）📽️": 16,
        "超清（CRF 18）": 18,
        "高清（CRF 20）": 20,
        "标准（CRF 22）": 22,
        "均衡（CRF 24）": 24,
        "压缩优化（CRF 26）": 26,
        "小体积（CRF 28）": 28,
        "极限压缩（CRF 30）⚡": 30,
    }
    quality_label = st.radio("选择压缩档位", list(crf_options.keys()), index=2)
    selected_crf = crf_options[quality_label]

    # 是否覆盖已有文件
    overwrite = st.checkbox("覆盖已有输出文件", value=False)

    # 开始执行
    if st.button("🚀 开始压缩视频"):
        if not input_dir or not os.path.exists(input_dir):
            st.warning("❗ 请输入有效的输入文件夹路径")
            return
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        video_files = sorted([
            f for f in os.listdir(input_dir)
            if f.lower().endswith((".mp4", ".mov", ".mkv"))
        ])

        if not video_files:
            st.warning("❗ 输入文件夹内没有找到视频文件")
            return

        total = len(video_files)
        progress = st.progress(0)

        for i, video_name in enumerate(video_files):
            in_path = os.path.join(input_dir, video_name)
            out_path = os.path.join(output_dir, video_name)

            if os.path.exists(out_path) and not overwrite:
                st.info(f"✅ {video_name} 已存在，跳过")
                progress.progress((i + 1) / total)
                continue

            st.write(f"🎬 正在压缩：{video_name}（CRF={selected_crf}）")

            clip = VideoFileClip(in_path)
            clip.write_videofile(
                out_path,
                codec="libx264",
                audio_codec="aac",
                preset="slow",
                ffmpeg_params=[
                    "-crf", str(selected_crf),
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                ],
                threads=4,
                fps=clip.fps,
                logger=None
            )
            clip.close()
            st.success(f"✅ 已完成：{video_name}")
            progress.progress((i + 1) / total)

        st.success("🎉 所有视频压缩完成！")


if __name__ == "__main__":
    batch_video_compress()