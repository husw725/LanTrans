import streamlit as st
import json
import os
import sys
import time
from pathlib import Path

import config  # 必须先于 moviepy 导入：config 会清理无效的 IMAGEMAGICK_BINARY
from ui_utils import validate_dir

from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from PIL import Image, ImageFont
import pysrt

# --- Configuration & Helpers ---

is_windows = os.name == "nt"
if is_windows:
    import moviepy.config as mpy_config
    imagemagick_binary = os.getenv("IMAGEMAGICK_BINARY")
    if imagemagick_binary and os.path.exists(imagemagick_binary):
        mpy_config.change_settings({"IMAGEMAGICK_BINARY": imagemagick_binary})

# 跨平台默认字体：优先 Arial 等拉丁字体（多数目标语言为拉丁文，且 .ttf 渲染最稳），
# CJK 字体仅作兜底。中日韩/泰/阿拉伯等非拉丁字幕请在右侧上传对应字体。
# 注意：避免把 .ttc（字体集合）作为默认——ImageMagick 渲染 .ttc 常常失败，会导致预览报错。
_FONT_CANDIDATES = {
    "win32": [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\msyh.ttc"],
    "darwin": ["/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
               "/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/PingFang.ttc"],
}.get(sys.platform, ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                     "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"])
default_font_path = next((p for p in _FONT_CANDIDATES if os.path.exists(p)), None)


def srt_time_to_seconds(t):
    return t.hours * 3600 + t.minutes * 60 + t.seconds + t.milliseconds / 1000


def safe_text(text):
    if not text:
        return ""
    cleaned = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\n\t")
    return cleaned.strip()


def wrap_text_pil(text, font_path, font_size, max_width):
    """Wraps text using PIL for accurate width calculation."""
    font = ImageFont.truetype(font_path, font_size)
    lines = []
    for paragraph in text.split('\n'):
        current_line = ""
        for word in paragraph.split(' '):
            if not word:
                continue
            test_line = f"{current_line} {word}".strip()
            try:
                line_width = font.getlength(test_line)
            except AttributeError:
                bbox = font.getbbox(test_line)
                line_width = bbox[2] - bbox[0]
            if line_width <= max_width:
                current_line = test_line
            else:
                lines.append(word if not current_line else current_line)
                current_line = word if current_line else ""
        if current_line:
            lines.append(current_line)
    return "\n".join(lines)


def generate_subtitle_clips(subs, w, h, style):
    clips = []
    shadow_offset = style.get("shadow_offset", (2, 2))
    shadow_font_size = style.get("shadow_font_size", style["font_size"])
    for sub in subs:
        safe_txt = safe_text(sub.text)
        if not safe_txt:
            continue
        wrapped_text = wrap_text_pil(safe_txt, style["font_path"], style["font_size"], style["max_text_width"])
        shadow_clip = TextClip(
            wrapped_text, fontsize=shadow_font_size, color=style["shadow_color"],
            method="label", align="center", font=style["font_path"]
        ).set_opacity(style["shadow_opacity"]).set_position(('center', h - style["bottom_offset"] + shadow_offset[1]))
        txt_clip = TextClip(
            wrapped_text, fontsize=style["font_size"], color=style["font_color"],
            stroke_color=style["stroke_color"], stroke_width=style["stroke_width"],
            method="label", align="center", font=style["font_path"]
        ).set_position(('center', h - style["bottom_offset"]))
        start, end = srt_time_to_seconds(sub.start), srt_time_to_seconds(sub.end)
        clips.append(shadow_clip.set_start(start).set_end(end))
        clips.append(txt_clip.set_start(start).set_end(end))
    return clips


def _save_style(style):
    config.STYLE_FILE.write_text(json.dumps(style, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_style():
    """优先用本次会话的样式，否则尝试从磁盘恢复上次的样式。"""
    if "subtitle_style" in st.session_state:
        return st.session_state["subtitle_style"]
    if config.STYLE_FILE.exists():
        try:
            style = json.loads(config.STYLE_FILE.read_text(encoding="utf-8"))
            style["shadow_offset"] = tuple(style.get("shadow_offset", (0, 2)))
            st.session_state["subtitle_style"] = style
            return style
        except (json.JSONDecodeError, OSError):
            pass
    return None


# --- Main Application ---
def run():
    if default_font_path is None:
        st.warning("⚠️ 未在系统中找到默认字体，请在「样式参数」中上传一个 .ttf 字体。")

    tab1, tab2 = st.tabs(["🎨 字幕样式设计", "📦 批量添加字幕"])

    # --- Tab 1: Style Designer ---
    with tab1:
        col1, col2 = st.columns([0.6, 0.4])

        with col1:
            st.subheader("🖼️ 实时预览")
            temp_video_path = Path("temp_preview_video.mp4")
            preview_video = st.file_uploader("选择一个视频用于字幕样式预览", type=["mp4", "mov", "mkv"])
            if preview_video:
                temp_video_path.write_bytes(preview_video.read())
                try:
                    with VideoFileClip(str(temp_video_path)) as clip:
                        st.session_state['preview_frame'] = Image.fromarray(clip.get_frame(1.0))
                        st.session_state['video_size'] = clip.size
                except Exception as e:
                    st.error(f"视频加载失败: {e}")
                    st.session_state.pop('preview_frame', None)

        with col2:
            st.subheader("⚙️ 样式参数")
            uploaded_font = st.file_uploader("上传自定义字体 (.ttf，非拉丁语言请上传对应字体)", type=["ttf", "ttc", "otf"])
            font_path = default_font_path
            if uploaded_font:
                font_path = "uploaded_font.ttf"
                Path(font_path).write_bytes(uploaded_font.read())
            else:
                st.caption(f"默认字体：`{Path(default_font_path).name if default_font_path else '未找到'}`"
                           "（拉丁语言适用；中日韩 / 泰 / 阿拉伯等请上传对应字体）")

            if 'video_size' in st.session_state and font_path:
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
                _save_style(style)
                st.success("✅ 样式已保存")
            elif not font_path:
                st.info("请先上传字体后再调整样式。")
            else:
                st.info("请先上传预览视频以加载样式参数。")

        if 'preview_frame' in st.session_state and 'subtitle_style' in st.session_state and temp_video_path.exists():
            with col1:
                style = st.session_state["subtitle_style"]
                w, h = st.session_state['video_size']
                # 默认用拉丁示例文本（与默认 Arial 字体匹配）；上传了自定义字体时
                # 追加一行中文，方便确认该字体能否渲染中日韩字形。
                preview_text = "Subtitle preview — this line is long enough to show wrapping."
                if uploaded_font:
                    preview_text += "\n字幕预览：换行效果展示。"
                try:
                    wrapped = wrap_text_pil(preview_text, style["font_path"], style["font_size"], style["max_text_width"])
                    txt_clip = TextClip(
                        wrapped, fontsize=style['font_size'], color=style['font_color'],
                        stroke_color=style['stroke_color'], stroke_width=style['stroke_width'],
                        method='label', align='center', font=style['font_path']
                    ).set_position(('center', h - style['bottom_offset']))
                    shadow_clip = TextClip(
                        wrapped, fontsize=style.get("shadow_font_size", style["font_size"]), color=style['shadow_color'],
                        method='label', align='center', font=style['font_path']
                    ).set_opacity(style['shadow_opacity']).set_position(('center', h - style['bottom_offset'] + style['shadow_offset'][1]))
                    with VideoFileClip(str(temp_video_path)) as base_clip:
                        final_clip = CompositeVideoClip([base_clip.subclip(0, 1), shadow_clip, txt_clip])
                        final_frame = final_clip.get_frame(0.5)
                    st.image(Image.fromarray(final_frame), caption="字幕样式预览")
                except Exception as e:
                    st.warning(f"⚠️ 预览渲染失败（通常是字体或 ImageMagick 问题）：{e}\n"
                               f"请尝试上传一个标准 .ttf 字体；非拉丁语言需上传对应字体。")

    # --- Tab 2: Batch Processing ---
    with tab2:
        style = _load_style()
        if style:
            st.success(f"当前已加载样式：字号 {style['font_size']}、颜色 {style['font_color']}、距底部 {style['bottom_offset']}px")
        else:
            st.warning("尚未设置样式，请先在「字幕样式设计」选项卡中设计并保存。")

        with st.container(border=True):
            st.subheader("📁 路径设置")
            p_col1, p_col2, p_col3 = st.columns(3)
            with p_col1:
                video_dir = st.text_input("视频文件夹路径")
                video_files = validate_dir(video_dir, exts=(".mp4", ".mov"))
            with p_col2:
                srt_dir = st.text_input("SRT 文件夹路径")
                srt_files = validate_dir(srt_dir, exts=(".srt",))
            with p_col3:
                output_dir = st.text_input("输出文件夹路径")

        with st.container(border=True):
            st.subheader("⚙️ 处理选项")
            s_col1, s_col2 = st.columns(2)
            with s_col1:
                match_mode = st.radio("SRT 匹配方式", ("按文件名匹配", "按顺序对应"))
            with s_col2:
                crf = st.select_slider("输出压缩质量", options=[18, 20, 23, 28], value=23,
                                       help="CRF值越低，质量越高体积越大。18高质量, 23均衡, 28小体积。")

        st.divider()
        if st.button("🚀 开始批量添加字幕", type="primary", use_container_width=True):
            if not style:
                st.warning("请先在「字幕样式设计」选项卡中设置并保存样式！")
                return
            if not (video_files and output_dir):
                st.warning("请确保视频文件夹有效，并填写输出文件夹路径。")
                return
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            srt_files = srt_files or []

            progress = st.progress(0, "准备开始...")
            log_container = st.container(height=300, border=True)
            for i, video_name in enumerate(video_files):
                progress.progress((i + 1) / len(video_files), f"正在处理 {i + 1}/{len(video_files)}: {video_name}（编码较慢，请耐心等待）")
                video_path = Path(video_dir) / video_name
                output_path = Path(output_dir) / video_name
                if "文件名" in match_mode:
                    srt_name = Path(video_name).stem + ".srt"
                elif i < len(srt_files):
                    srt_name = srt_files[i]
                else:
                    log_container.warning(f"⚠️ {video_name} 没有对应的 SRT（按顺序对应不足），跳过。")
                    continue
                srt_path = Path(srt_dir) / srt_name

                if not srt_path.exists():
                    log_container.warning(f"⚠️ {video_name} 对应的 SRT ({srt_name}) 未找到，跳过。")
                    continue
                try:
                    t0 = time.time()
                    with VideoFileClip(str(video_path)) as video_clip:
                        subs = pysrt.open(str(srt_path), encoding='utf-8')
                        subtitle_clips = generate_subtitle_clips(subs, video_clip.w, video_clip.h, style)
                        final_video = CompositeVideoClip([video_clip, *subtitle_clips])
                        final_video.write_videofile(
                            str(output_path), codec="libx264", audio_codec="aac", preset="slow",
                            ffmpeg_params=["-crf", str(crf)], threads=4, logger=None
                        )
                        final_video.close()
                    log_container.success(f"✅ {video_name} 已处理完成（耗时 {time.time() - t0:.0f}s）。")
                except Exception as e:
                    log_container.error(f"❌ 处理 {video_name} 时出错: {e}")

            st.balloons()
            st.success("🎉 所有视频已处理完成！")
