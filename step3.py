import streamlit as st
from pathlib import Path
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
import pysrt
import os

def run():
    st.header("Step 3: 视频添加字幕 & 字幕位置可视化调整")

    # ---------- 选择预览视频 ----------
    st.subheader("字幕位置预览")
    video_file = st.file_uploader("选择视频文件用于预览", type=["mp4", "mov", "mkv"])
    srt_file = st.file_uploader("选择对应的 SRT 文件", type=["srt"])
    subtitle_bottom = st.slider("字幕底部距离视频底边 (像素)", 10, 200, 50)

    if video_file and srt_file:
        # 临时保存上传文件
        temp_video_path = Path("temp_preview_video.mp4")
        temp_srt_path = Path("temp_preview.srt")
        with open(temp_video_path, "wb") as f:
            f.write(video_file.read())
        with open(temp_srt_path, "wb") as f:
            f.write(srt_file.read())

        clip = VideoFileClip(str(temp_video_path))
        w, h = clip.size
        subs = pysrt.open(str(temp_srt_path))

        # 生成第一帧带字幕预览
        first_sub = subs[0] if subs else None
        if first_sub:
            txt_clip = TextClip(first_sub.text, fontsize=24, color='white', stroke_color='black', stroke_width=1)
            txt_clip = txt_clip.set_position(("center", h - subtitle_bottom))
            txt_clip = txt_clip.set_start(first_sub.start.seconds)
            txt_clip = txt_clip.set_end(first_sub.end.seconds)
            preview_clip = CompositeVideoClip([clip.subclip(0, first_sub.end.seconds), txt_clip])
        else:
            preview_clip = clip.subclip(0, 5)  # 如果没有字幕，截取前5秒

        preview_frame = preview_clip.get_frame(0.5)  # 获取0.5秒帧
        from PIL import Image
        st.image(Image.fromarray(preview_frame))

    # ---------- 批量处理视频 ----------
    st.subheader("批量添加字幕到视频")
    video_dir = st.text_input("视频文件夹路径")
    srt_dir = st.text_input("SRT 文件夹路径")
    output_dir = st.text_input("输出视频文件夹路径")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    batch_bottom = st.slider("字幕底部距离视频底边 (像素) - 批量", 10, 200, 50)

    if st.button("开始批量添加字幕"):
        if not video_dir or not os.path.exists(video_dir):
            st.warning("请提供有效的视频文件夹路径")
        elif not srt_dir or not os.path.exists(srt_dir):
            st.warning("请提供有效的 SRT 文件夹路径")
        else:
            video_files = sorted([f for f in os.listdir(video_dir) if f.lower().endswith((".mp4", ".mov", ".mkv"))])
            srt_files = sorted([f for f in os.listdir(srt_dir) if f.lower().endswith(".srt")])

            if not video_files or not srt_files:
                st.warning("视频或字幕文件夹为空")
            else:
                for video_file in video_files:
                    video_path = os.path.join(video_dir, video_file)
                    srt_file = next((f for f in srt_files if Path(f).stem == Path(video_file).stem), None)
                    if not srt_file:
                        st.warning(f"{video_file} 没有找到对应的 SRT，跳过")
                        continue

                    srt_path = os.path.join(srt_dir, srt_file)
                    output_path = os.path.join(output_dir, video_file)
                    if os.path.exists(output_path):
                        st.info(f"{video_file} 已处理，跳过")
                        continue

                    clip = VideoFileClip(video_path)
                    w, h = clip.size
                    subs = pysrt.open(srt_path)
                    subtitle_clips = []

                    for sub in subs:
                        txt_clip = TextClip(sub.text, fontsize=24, color='white', stroke_color='black', stroke_width=1)
                        txt_clip = txt_clip.set_position(("center", h - batch_bottom))
                        txt_clip = txt_clip.set_start(sub.start.seconds + sub.start.microseconds/1e6)
                        txt_clip = txt_clip.set_end(sub.end.seconds + sub.end.microseconds/1e6)
                        subtitle_clips.append(txt_clip)

                    video = CompositeVideoClip([clip, *subtitle_clips])
                    video.write_videofile(output_path, codec="libx264", audio_codec="aac")

                    st.success(f"{video_file} 已处理完成")
