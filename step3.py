import streamlit as st
from pathlib import Path
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from PIL import Image, ImageFont
import pysrt
import os
from dotenv import load_dotenv
load_dotenv()

# --- Configuration & Helpers ---

is_windows = os.name == "nt"
if is_windows:
    import moviepy.config as mpy_config
    imagemagick_binary = os.getenv("IMAGEMAGICK_BINARY")
    if imagemagick_binary and os.path.exists(imagemagick_binary):
        mpy_config.change_settings({"IMAGEMAGICK_BINARY": imagemagick_binary})
    default_font_path = r"C:\Windows\Fonts\arial.ttf"
else:
    default_font_path = "Arial"

def srt_time_to_seconds(t):
    return t.hours * 3600 + t.minutes * 60 + t.seconds + t.milliseconds / 1000

def safe_text(text):
    if not text: return ""
    cleaned = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\n\t")
    return cleaned.strip()

def wrap_text_pil(text, font_path, font_size, max_width):
    """Wraps text using PIL for accurate width calculation."""
    font = ImageFont.truetype(font_path, font_size)
    lines = []
    
    for paragraph in text.split('\n'):
        words = paragraph.split(' ')
        current_line = ""
        for word in words:
            if not word: continue
            
            test_line = f"{current_line} {word}".strip()
            
            try:
                line_width = font.getlength(test_line)
            except AttributeError:
                bbox = font.getbbox(test_line)
                line_width = bbox[2] - bbox[0]

            if line_width <= max_width:
                current_line = test_line
            else:
                if not current_line:
                    lines.append(word)
                else:
                    lines.append(current_line)
                    current_line = word
        
        if current_line:
            lines.append(current_line)
            
    return "\n".join(lines)

def generate_subtitle_clips(subs, w, h, style):
    clips = []
    shadow_offset = style.get("shadow_offset", (2, 2))
    shadow_font_size = style.get("shadow_font_size", style["font_size"])

    for sub in subs:
        safe_txt = safe_text(sub.text)
        if not safe_txt: continue

        wrapped_text = wrap_text_pil(safe_txt, style["font_path"], style["font_size"], style["max_text_width"])

        # Shadow Layer
        shadow_clip = TextClip(
            wrapped_text, fontsize=shadow_font_size, color=style["shadow_color"],
            method="label", align="center", font=style["font_path"]
        ).set_opacity(style["shadow_opacity"]).set_position((
            'center', h - style["bottom_offset"] + shadow_offset[1]
        ))
        
        # Text Layer
        txt_clip = TextClip(
            wrapped_text, fontsize=style["font_size"], color=style["font_color"],
            stroke_color=style["stroke_color"], stroke_width=style["stroke_width"],
            method="label", align="center", font=style["font_path"]
        ).set_position(('center', h - style["bottom_offset"]))
        
        start, end = srt_time_to_seconds(sub.start), srt_time_to_seconds(sub.end)
        shadow_clip = shadow_clip.set_start(start).set_end(end)
        txt_clip = txt_clip.set_start(start).set_end(end)
        clips.extend([shadow_clip, txt_clip])
    return clips

# --- Main Application ---
def run():
    st.header("🎨 Step 3: 添加视频字幕")
    st.caption("可视化设计字幕样式，并将其批量应用到视频中。")

    tab1, tab2 = st.tabs(["🎨 字幕样式设计", "📦 批量添加字幕"])

    # --- Tab 1: Style Designer ---
    with tab1:
        col1, col2 = st.columns([0.6, 0.4])
        
        with col1:
            st.subheader("🖼️ 实时预览")
            preview_video = st.file_uploader("选择一个视频用于字幕样式预览", type=["mp4", "mov", "mkv"])
            
            if preview_video:
                temp_video_path = Path("temp_preview_video.mp4")
                with open(temp_video_path, "wb") as f:
                    f.write(preview_video.read())
                
                try:
                    with VideoFileClip(str(temp_video_path)) as clip:
                        frame = clip.get_frame(1.0) # Get a frame for preview background
                        st.session_state['preview_frame'] = Image.fromarray(frame)
                        st.session_state['video_size'] = clip.size
                except Exception as e:
                    st.error(f"视频加载失败: {e}")
                    del st.session_state['preview_frame']

        with col2:
            st.subheader("⚙️ 样式参数")
            
            uploaded_font = st.file_uploader("上传自定义字体 (.ttf)", type=["ttf"])
            font_path = default_font_path
            if uploaded_font:
                font_path = Path("uploaded_font.ttf")
                with open(font_path, "wb") as f: f.write(uploaded_font.read())

            if 'video_size' in st.session_state:
                w, h = st.session_state['video_size']
                
                with st.container(border=True):
                    st.markdown("**字体与颜色**")
                    font_size = st.slider("字体大小", 12, 100, 48)
                    font_color = st.color_picker("字体颜色", "#FFFFFF")
                with st.container(border=True):
                    st.markdown("**描边**")
                    stroke_width = st.slider("描边宽度", 0, 5, 1)
                    stroke_color = st.color_picker("描边颜色", "#000000")
                with st.container(border=True):
                    st.markdown("**位置与尺寸**")
                    bottom_offset = st.slider("距底部距离(px)", 0, h // 2, 80)
                    width_ratio = st.slider("最大宽度比例", 0.2, 1.0, 0.8, step=0.05)
                with st.container(border=True):
                    st.markdown("**阴影**")
                    shadow_opacity = st.slider("阴影不透明度", 0.0, 1.0, 0.5)
                    shadow_color = st.color_picker("阴影颜色", "#000000")
                    shadow_offset_y = st.slider("阴影垂直偏移(px)", -10, 10, 2)

                style = {
                    "font_path": str(font_path), "font_size": font_size, "font_color": font_color,
                    "stroke_color": stroke_color, "stroke_width": stroke_width, "bottom_offset": bottom_offset,
                    "max_text_width": int(w * width_ratio), "shadow_color": shadow_color,
                    "shadow_opacity": shadow_opacity, "shadow_offset": (0, shadow_offset_y),
                }
                st.session_state["subtitle_style"] = style
                st.success("✅ 样式已暂存")

        if 'preview_frame' in st.session_state and 'subtitle_style' in st.session_state:
            with col1:
                style = st.session_state["subtitle_style"]
                preview_img = st.session_state['preview_frame'].copy()
                w, h = st.session_state['video_size']

                # Create a dummy subtitle clip for preview
                preview_text = "这是字幕预览，这段文字会展示换行效果。"
                wrapped_preview_text = wrap_text_pil(preview_text, style["font_path"], style["font_size"], style["max_text_width"])

                txt_clip_preview = TextClip(
                    wrapped_preview_text, fontsize=style['font_size'], color=style['font_color'],
                    stroke_color=style['stroke_color'], stroke_width=style['stroke_width'],
                    method='label', align='center', font=style['font_path']
                ).set_position(('center', h - style['bottom_offset']))
                
                shadow_font_size = style.get("shadow_font_size", style["font_size"])
                shadow_clip_preview = TextClip(
                    wrapped_preview_text, fontsize=shadow_font_size, color=style['shadow_color'],
                    method='label', align='center', font=style['font_path']
                ).set_opacity(style['shadow_opacity']).set_position(('center', h - style['bottom_offset'] + style['shadow_offset'][1]))

                # Composite onto the frame
                final_clip = CompositeVideoClip([VideoFileClip(str(temp_video_path)).subclip(0,1), shadow_clip_preview, txt_clip_preview])
                final_frame = final_clip.get_frame(0.5)
                st.image(Image.fromarray(final_frame), caption="字幕样式预览")

    # --- Tab 2: Batch Processing ---
    with tab2:
        with st.container(border=True):
            st.subheader("📁 路径设置")
            p_col1, p_col2, p_col3 = st.columns(3)
            with p_col1: video_dir = st.text_input("视频文件夹路径")
            with p_col2: srt_dir = st.text_input("SRT 文件夹路径")
            with p_col3: output_dir = st.text_input("输出文件夹路径")
        
        with st.container(border=True):
            st.subheader("⚙️ 处理选项")
            s_col1, s_col2 = st.columns(2)
            with s_col1: match_mode = st.radio("SRT 匹配方式", ("按文件名匹配", "按顺序对应"))
            with s_col2:
                crf = st.select_slider("输出压缩质量", options=[18, 20, 23, 28], value=23, help="CRF值越低，质量越高体积越大。18高质量, 23均衡, 28小体积。")

        st.divider()
        if st.button("🚀 开始批量添加字幕", type="primary", use_container_width=True):
            if "subtitle_style" not in st.session_state:
                st.warning("请先在“字幕样式设计”选项卡中设置并暂存样式！")
                return
            # (Validation and processing logic remains similar to original)
            style = st.session_state["subtitle_style"]
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            video_files = sorted([f for f in os.listdir(video_dir) if f.lower().endswith((".mp4", ".mov"))])
            srt_files = sorted([f for f in os.listdir(srt_dir) if f.lower().endswith(".srt")])

            progress_bar = st.progress(0, "准备开始...")
            log_container = st.container(height=300, border=True)

            for i, video_name in enumerate(video_files):
                progress_bar.progress((i + 1) / len(video_files), f"正在处理: {video_name}")
                # ... (rest of the file processing logic is largely the same)
                video_path = Path(video_dir) / video_name
                output_path = Path(output_dir) / video_name
                srt_name = Path(video_name).stem + ".srt" if "文件名" in match_mode else srt_files[i]
                srt_path = Path(srt_dir) / srt_name

                if not srt_path.exists():
                    log_container.warning(f"⚠️ {video_name} 对应的 SRT ({srt_name}) 未找到，跳过。")
                    continue
                
                try:
                    video_clip = VideoFileClip(str(video_path))
                    subs = pysrt.open(str(srt_path), encoding='utf-8')
                    subtitle_clips = generate_subtitle_clips(subs, video_clip.w, video_clip.h, style)
                    final_video = CompositeVideoClip([video_clip, *subtitle_clips])
                    final_video.write_videofile(
                        str(output_path), codec="libx264", audio_codec="aac", preset="slow",
                        ffmpeg_params=["-crf", str(crf)], threads=4
                    )
                    log_container.success(f"✅ {video_name} 已处理完成。")
                except Exception as e:
                    log_container.error(f"❌ 处理 {video_name} 时出错: {e}")

            st.balloons()
            st.success("🎉 所有视频已处理完成！")