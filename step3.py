import streamlit as st
from pathlib import Path
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from PIL import Image
import pysrt
import os

# check if running on windows
is_windows = os.name == "nt"
if is_windows:
    import moviepy.config as mpy_config
    mpy_config.change_settings({
        "IMAGEMAGICK_BINARY": r"C:\\Program Files\\ImageMagick-7.1.2-Q16-HDRI\\magick.exe"
    })
    default_font_path = r"C:\Windows\Fonts\arial.ttf"
else:
    default_font_path = "Arial"

# ===================== 工具函数 =====================
def srt_time_to_seconds(t):
    """将 pysrt.SubRipTime 转为秒(float)."""
    return t.hours * 3600 + t.minutes * 60 + t.seconds + t.milliseconds / 1000

def generate_subtitle_clips(subs, w, h, style):
    """根据 SRT 生成字幕 TextClip 列表."""
    clips = []
    shadow_offset = style.get("shadow_offset", (5, 5))

    for sub in subs:
        # 阴影层
        shadow_clip = TextClip(
            sub.text,
            fontsize=style["font_size"] + 1,
            color=style["shadow_color"],
            method="caption",
            size=(style["max_text_width"], None),
            align="center",
            font=style["font_path"],
        ).set_opacity(style["shadow_opacity"]).set_position((
            w / 2 - style["max_text_width"] / 2 + shadow_offset[0],
            h - style["bottom_offset"] + shadow_offset[1]
        ))

        # 主文字层
        txt_clip = TextClip(
            sub.text,
            fontsize=style["font_size"],
            color=style["font_color"],
            stroke_color=style["stroke_color"],
            stroke_width=style["stroke_width"],
            method="caption",
            size=(style["max_text_width"], None),
            align="center",
            font=style["font_path"],
        ).set_position(("center", h - style["bottom_offset"]))

        start = srt_time_to_seconds(sub.start)
        end = srt_time_to_seconds(sub.end)
        shadow_clip = shadow_clip.set_start(start).set_end(end)
        txt_clip = txt_clip.set_start(start).set_end(end)

        clips.extend([shadow_clip, txt_clip])
    return clips


# ===================== 主程序 =====================
def run():
    st.header("🎬 Step 3: 字幕样式调整 + 批量视频加字幕")

    # ---------- Step 1: 样式预览 ----------
    st.subheader("🎨 Step 1: 字幕样式可视化调整")
    preview_video = st.file_uploader("选择一个视频用于字幕样式预览", type=["mp4", "mov", "mkv"])

    uploaded_font = st.sidebar.file_uploader("上传自定义字体 (.ttf)", type=["ttf"])
    font_path = default_font_path
    if uploaded_font:
        font_path = Path("uploaded_font.ttf")
        with open(font_path, "wb") as f:
            f.write(uploaded_font.read())
        st.sidebar.success("✅ 自定义字体已加载")

    if preview_video:
        temp_video_path = Path("temp_preview_video.mp4")
        with open(temp_video_path, "wb") as f:
            f.write(preview_video.read())

        clip = VideoFileClip(str(temp_video_path))
        w, h = clip.size

        st.sidebar.header("🎨 字幕样式设置")
        subtitle_text = "I am subtitle"
        font_size = st.sidebar.slider("字体大小", 12, 80, 36)
        font_color = st.sidebar.color_picker("字体颜色", "#FFFFFF")
        stroke_color = st.sidebar.color_picker("描边颜色", "#ffffff")
        stroke_width = st.sidebar.slider("描边宽度", 0, 5, 1)
        bottom_offset = st.sidebar.slider("字幕距离视频底部 (像素)", 0, 1000, 100)
        width_ratio = st.sidebar.slider("字幕最大宽度占视频比例", 0.2, 1.0, 0.6, step=0.05)

        # 阴影参数
        shadow_color = st.sidebar.color_picker("阴影颜色", "#000000")
        shadow_opacity = st.sidebar.slider("阴影透明度", 0.0, 1.0, 0.6, step=0.05)
        shadow_offset_x = st.sidebar.slider("阴影水平偏移 (像素)", -20, 20, 5)
        shadow_offset_y = st.sidebar.slider("阴影垂直偏移 (像素)", -20, 20, 5)
        shadow_offset = (shadow_offset_x, shadow_offset_y)

        max_text_width = int(w * width_ratio)

        shadow_clip = TextClip(
            subtitle_text,
            fontsize=font_size + 1,
            color=shadow_color,
            method="caption",
            size=(max_text_width, None),
            align="center",
            font=font_path,
        ).set_opacity(shadow_opacity).set_position(("center", h - bottom_offset + shadow_offset[1]))

        txt_clip = TextClip(
            subtitle_text,
            fontsize=font_size,
            color=font_color,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            method="caption",
            size=(max_text_width, None),
            align="center",
            font=font_path,
        ).set_position(("center", h - bottom_offset))

        preview_clip = CompositeVideoClip([clip.subclip(0, 5), shadow_clip, txt_clip])
        frame = preview_clip.get_frame(1.0)
        st.image(Image.fromarray(frame), caption="字幕样式预览")

        style = {
            "font_path": str(font_path),
            "font_size": font_size,
            "font_color": font_color,
            "stroke_color": stroke_color,
            "stroke_width": stroke_width,
            "bottom_offset": bottom_offset,
            "max_text_width": max_text_width,
            "shadow_color": shadow_color,
            "shadow_opacity": shadow_opacity,
            "shadow_offset": shadow_offset,
        }
        st.session_state["subtitle_style"] = style
        st.success("✅ 样式设置已保存，可用于批量字幕添加。")

    # ---------- Step 2: 批量加字幕 ----------
    st.subheader("📦 Step 2: 批量为视频添加字幕")

    video_dir = st.text_input("视频文件夹路径")
    srt_dir = st.text_input("SRT 文件夹路径")
    output_dir = st.text_input("输出视频文件夹路径")

    match_mode = st.radio("选择 SRT 匹配方式", ("按文件名匹配同名 SRT", "按排序顺序对应"))

    # 💡 增加压缩质量档位选项
    st.markdown("### 🎚️ 输出质量设置")
    crf_options = {
        "高质量（CRF 18）": 18,
        "标准（CRF 20）": 20,
        "均衡（CRF 23）": 23,
        "小体积（CRF 28）": 28,
    }
    quality_label = st.radio("选择压缩档位", list(crf_options.keys()), index=1)
    selected_crf = crf_options[quality_label]

    if st.button("🚀 开始批量添加字幕"):
        if "subtitle_style" not in st.session_state:
            st.warning("请先在上方调整并保存字幕样式！")
            return

        style = st.session_state["subtitle_style"]
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        if not os.path.exists(video_dir) or not os.path.exists(srt_dir):
            st.warning("请提供有效的视频和 SRT 文件夹路径。")
            return

        video_files = sorted([f for f in os.listdir(video_dir) if f.lower().endswith((".mp4", ".mov", ".mkv"))])
        srt_files = sorted([f for f in os.listdir(srt_dir) if f.lower().endswith(".srt")])

        if not video_files or not srt_files:
            st.warning("视频或字幕文件夹为空。")
            return

        if match_mode == "按排序顺序对应" and len(video_files) != len(srt_files):
            st.warning("⚠️ 视频文件数量与 SRT 文件数量不一致！")
            return

        progress = st.progress(0)
        total = len(video_files)

        for i, video_name in enumerate(video_files):
            video_path = os.path.join(video_dir, video_name)

            if match_mode == "按文件名匹配同名 SRT":
                srt_name = Path(video_name).stem + ".srt"
            else:
                srt_name = srt_files[i]

            srt_path = os.path.join(srt_dir, srt_name)
            output_path = os.path.join(output_dir, video_name)

            if not os.path.exists(srt_path):
                st.warning(f"⚠️ {video_name} 没有找到对应的 SRT ({srt_name})，跳过")
                continue

            if os.path.exists(output_path):
                st.info(f"✅ {video_name} 已存在，跳过")
                continue

            clip = VideoFileClip(video_path)
            w, h = clip.size
            style["max_text_width"] = int(w * (style["max_text_width"] / w))

            subs = pysrt.open(srt_path)
            subtitle_clips = generate_subtitle_clips(subs, w, h, style)

            video = CompositeVideoClip([clip, *subtitle_clips])
            st.write(f"🎞️ 正在处理: {video_name}（CRF={selected_crf}）")

            video.write_videofile(
                output_path,
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

            progress.progress((i + 1) / total)
            st.success(f"✅ {video_name} 已处理完成")

        st.success("🎉 所有视频已处理完成！")


if __name__ == "__main__":
    run()