import streamlit as st
from pathlib import Path
from moviepy import VideoFileClip, TextClip, CompositeVideoClip
from PIL import Image, ImageDraw, ImageFont
import pysrt
import os

# ===================== 工具函数 =====================
def srt_time_to_seconds(t):
    """Convert pysrt.SubRipTime to seconds."""
    return t.hours * 3600 + t.minutes * 60 + t.seconds + t.milliseconds / 1000

def make_text_clip(text, style):
    """
    Create a TextClip with optional outline (stroke) using Pillow.
    """
    font_path = style.get("font_path")  # Optional: path to .ttf font
    font_size = style["font_size"]
    font_color = style["font_color"]
    stroke_color = style["stroke_color"]
    stroke_width = style["stroke_width"]
    max_width = style["max_text_width"]

    # Fallback font
    font = ImageFont.truetype(font_path if font_path else "arial.ttf", font_size)

    # Prepare image size
    dummy_img = Image.new("RGBA", (max_width, font_size*3), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy_img)
    # Wrap text to fit max_width
    lines = []
    words = text.split()
    current_line = ""
    for w in words:
        test_line = current_line + (" " if current_line else "") + w
        line_width, _ = draw.textsize(test_line, font=font)
        if line_width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = w
    if current_line:
        lines.append(current_line)

    # Calculate height
    line_height = draw.textsize("A", font=font)[1]
    img_height = line_height * len(lines) + stroke_width*2
    img = Image.new("RGBA", (max_width, img_height), (0,0,0,0))
    draw = ImageDraw.Draw(img)

    # Draw text with outline
    y = 0
    for line in lines:
        x = 0
        for dx in range(-stroke_width, stroke_width+1):
            for dy in range(-stroke_width, stroke_width+1):
                if dx != 0 or dy != 0:
                    draw.text((x+dx, y+dy), line, font=font, fill=stroke_color)
        draw.text((x, y), line, font=font, fill=font_color)
        y += line_height

    return TextClip(img, ismask=False)

def generate_subtitle_clips(subs, h, style):
    """Generate a list of subtitle TextClips from SRT."""
    clips = []
    for sub in subs:
        txt_clip = make_text_clip(sub.text, style)
        txt_clip = txt_clip.set_position(("center", h - style["bottom_offset"]))
        start = srt_time_to_seconds(sub.start)
        end = srt_time_to_seconds(sub.end)
        txt_clip = txt_clip.set_start(start).set_end(end)
        clips.append(txt_clip)
    return clips


# ===================== 主程序 =====================
def run():
    st.header("🎬 Step 3: 字幕样式调整 + 批量视频加字幕")

    # ---------- Step 1: 样式预览 ----------
    st.subheader("🎨 Step 1: 字幕样式可视化调整")
    preview_video = st.file_uploader("选择一个视频用于字幕样式预览", type=["mp4", "mov", "mkv"])

    if preview_video:
        temp_video_path = Path("temp_preview_video.mp4")
        with open(temp_video_path, "wb") as f:
            f.write(preview_video.read())

        clip = VideoFileClip(str(temp_video_path))
        w, h = clip.size

        st.sidebar.header("🎨 字幕样式设置")
        font_size = st.sidebar.slider("字体大小", 12, 80, 36)
        font_color = st.sidebar.color_picker("字体颜色", "#FFFFFF")
        stroke_color = st.sidebar.color_picker("描边颜色", "#000000")
        stroke_width = st.sidebar.slider("描边宽度", 0, 5, 2)
        bottom_offset = st.sidebar.slider("字幕距离视频底部 (像素)", 0, 300, 100)
        width_ratio = st.sidebar.slider("字幕最大宽度占视频比例", 0.2, 1.0, 0.6, step=0.05)

        max_text_width = int(w * width_ratio)

        # Demo subtitle for preview
        style = {
            "font_size": font_size,
            "font_color": font_color,
            "stroke_color": stroke_color,
            "stroke_width": stroke_width,
            "bottom_offset": bottom_offset,
            "max_text_width": max_text_width,
            "font_path": None,  # Optional: provide ttf file
        }

        txt_clip = make_text_clip("I am subtitle", style)
        txt_clip = txt_clip.set_position(("center", h - bottom_offset))
        txt_clip = txt_clip.set_duration(5)

        preview_clip = CompositeVideoClip([clip.subclip(0, 5), txt_clip])
        frame = preview_clip.get_frame(1.0)
        st.image(Image.fromarray(frame), caption="字幕样式预览", use_column_width=True)

        st.session_state["subtitle_style"] = style
        st.success("✅ 样式设置已保存，可用于批量字幕添加。")

    # ---------- Step 2: 批量加字幕 ----------
    st.subheader("📦 Step 2: 批量为视频添加字幕")
    video_dir = st.text_input("视频文件夹路径")
    srt_dir = st.text_input("SRT 文件夹路径")
    output_dir = st.text_input("输出视频文件夹路径")

    if st.button("🚀 开始批量添加字幕"):
        if "subtitle_style" not in st.session_state:
            st.warning("请先在上方调整并保存字幕样式！")
            return

        style = st.session_state["subtitle_style"]
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        video_files = sorted([f for f in os.listdir(video_dir) if f.lower().endswith((".mp4", ".mov", ".mkv"))])
        srt_files = sorted([f for f in os.listdir(srt_dir) if f.lower().endswith(".srt")])

        total = len(video_files)
        progress = st.progress(0)

        for i, video_name in enumerate(video_files):
            video_path = os.path.join(video_dir, video_name)
            srt_name = Path(video_name).stem + ".srt"
            srt_path = os.path.join(srt_dir, srt_name)
            output_path = os.path.join(output_dir, video_name)

            if not os.path.exists(srt_path):
                st.warning(f"{video_name} 没有找到对应的 SRT，跳过")
                continue
            if os.path.exists(output_path):
                st.info(f"{video_name} 已存在，跳过")
                continue

            clip = VideoFileClip(video_path)
            w, h = clip.size
            style["max_text_width"] = int(w * (style["max_text_width"] / w))

            subs = pysrt.open(srt_path)
            subtitle_clips = generate_subtitle_clips(subs, h, style)

            video = CompositeVideoClip([clip, *subtitle_clips])
            st.write(f"🎞️ 正在处理: {video_name}")
            video.write_videofile(output_path, codec="libx264", audio_codec="aac", threads=4, logger=None, preset="ultrafast")

            progress.progress((i + 1) / total)
            st.success(f"✅ {video_name} 已处理完成")

        st.success("🎉 所有视频已处理完成！")


if __name__ == "__main__":
    run()