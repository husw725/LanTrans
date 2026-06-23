import streamlit as st
import json
import os
import sys
import time
from functools import lru_cache
from pathlib import Path

import config  # 必须先于 moviepy 导入：config 会清理无效的 IMAGEMAGICK_BINARY
from ui_utils import validate_dir

import numpy as np
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
from PIL import Image, ImageFont, ImageDraw
import pysrt

# --- Configuration & Helpers ---
# 字幕渲染统一用 PIL（见 render_block），不再依赖 ImageMagick/TextClip：
# 预览与烧录像素级一致，也免去了 Windows 配置 IMAGEMAGICK_BINARY 的麻烦。

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


def _is_breakable_char(ch):
    """无空格断行语言（中日韩、泰文及全角标点）——可在字符之间换行。"""
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF or   # CJK 统一表意文字
            0x3040 <= o <= 0x30FF or   # 日文平假名 / 片假名
            0xAC00 <= o <= 0xD7A3 or   # 韩文谚文
            0x0E00 <= o <= 0x0E7F or   # 泰文
            0x3000 <= o <= 0x303F or   # CJK 标点
            0xFF00 <= o <= 0xFFEF)     # 全角字符


def _is_combining_mark(ch):
    """组合附加符号 / 泰文元音声调符号——不应出现在行首，需附着到前一字符。"""
    o = ord(ch)
    return (0x0300 <= o <= 0x036F or
            o == 0x0E31 or 0x0E34 <= o <= 0x0E3A or 0x0E47 <= o <= 0x0E4E)


# 避头尾：这些标点不应出现在行首，需并入上一行行尾
_LEADING_FORBIDDEN = "，。、！？；：）】》」』’”·.,!?;:)]}>"


def _apply_kinsoku(lines):
    """把出现在行首的收尾标点移到上一行末尾（中日韩避头尾规则的简化版）。"""
    out = []
    for line in lines:
        while out and line and line[0] in _LEADING_FORBIDDEN:
            out[-1] += line[0]
            line = line[1:]
        if line:
            out.append(line)
    return out


@lru_cache(maxsize=16)
def _get_font(font_path, font_size):
    """缓存字体对象，避免一集数百条字幕时反复从磁盘加载。"""
    return ImageFont.truetype(font_path, font_size)


def wrap_text_pil(text, font_path, font_size, max_width):
    """按像素宽度换行。拉丁文按单词换行；中日韩/泰文等无空格语言按字符换行。"""
    font = _get_font(font_path, font_size)

    def width(s):
        try:
            return font.getlength(s)
        except AttributeError:
            bbox = font.getbbox(s)
            return bbox[2] - bbox[0]

    lines = []
    for paragraph in text.split('\n'):
        # 切成原子：空格、拉丁单词、单个 CJK/泰文字符
        atoms, buf = [], ""
        for ch in paragraph:
            if _is_combining_mark(ch):
                if buf:
                    buf += ch
                elif atoms:
                    atoms[-1] += ch
                else:
                    buf += ch
            elif ch == ' ' or _is_breakable_char(ch):
                if buf:
                    atoms.append(buf)
                    buf = ""
                atoms.append(ch)
            else:
                buf += ch
        if buf:
            atoms.append(buf)

        para_lines, current = [], ""
        for atom in atoms:
            if atom == ' ' and not current:
                continue  # 跳过行首空格
            tentative = current + atom
            if not current or width(tentative) <= max_width:
                current = tentative
            else:
                para_lines.append(current.rstrip())
                current = "" if atom == ' ' else atom
        if current.strip():
            para_lines.append(current.rstrip())
        # 避头尾仅在同一段（同一原始行）内处理，避免跨行合并
        lines.extend(_apply_kinsoku(para_lines))
    return "\n".join(lines)


def generate_subtitle_clips(subs, w, h, style):
    """为每条字幕生成一个【紧凑】定位的透明 ImageClip（与预览同一套 PIL 渲染）。"""
    clips = []
    for sub in subs:
        safe_txt = safe_text(sub.text)
        if not safe_txt:
            continue
        block, x, y = render_block((w, h), safe_txt, style)
        start, end = srt_time_to_seconds(sub.start), srt_time_to_seconds(sub.end)
        clip = ImageClip(np.array(block), transparent=True).set_position((x, y)).set_start(start).set_end(end)
        clips.append(clip)
    return clips


def _hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _wrap_and_fit(text, style):
    """换行，并在设置了 max_lines 时自动缩小字号以满足行数上限。
    返回 (换行后文本, 实际字号)。"""
    fs = style["font_size"]
    max_lines = style.get("max_lines", 0)
    while True:
        wrapped = wrap_text_pil(text, style["font_path"], fs, style["max_text_width"])
        if not max_lines or wrapped.count("\n") + 1 <= max_lines or fs <= 12:
            return wrapped, fs
        fs -= 2


_SCRATCH = ImageDraw.Draw(Image.new("RGBA", (1, 1)))


def render_block(frame_size, text, style):
    """把单条字幕渲染成一张【紧凑】RGBA 小图（背景条+阴影+描边+伪加粗+文字），
    返回 (img, x, y) 左上角粘贴坐标。预览与烧录共用，保证所见即所得。
    用小图而非整帧图层：合成成本随文字块大小而非画面分辨率，烧录才不会慢。"""
    W, H = frame_size
    wrapped, fs = _wrap_and_fit(text, style)
    font = _get_font(style["font_path"], fs)
    bold = style.get("bold", 0)
    outline = style.get("stroke_width", 0)
    spacing = style.get("line_spacing", max(2, int(fs * 0.2)))
    total = outline + bold
    sx, sy = style.get("shadow_offset", (0, 2)) if style.get("shadow_opacity", 0) > 0 else (0, 0)
    common = dict(font=font, anchor="la", align="center", spacing=spacing)

    l, t, r, b = _SCRATCH.multiline_textbbox((0, 0), wrapped, stroke_width=total, **common)
    pad = style.get("bg_padding", 12) if style.get("bg_enabled") else max(2, total)
    bw = (r - l) + 2 * pad + abs(sx)
    bh = (b - t) + 2 * pad + abs(sy)
    block = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(block)
    tx = pad - l + max(0, -sx)   # 文字绘制基点，使内容含 pad 并为阴影方向留白
    ty = pad - t + max(0, -sy)

    if style.get("bg_enabled"):
        bg = _hex_to_rgb(style.get("bg_color", "#000000")) + (int(255 * style.get("bg_opacity", 0.5)),)
        d.rounded_rectangle([tx + l - pad, ty + t - pad, tx + r + pad, ty + b + pad],
                            radius=style.get("bg_radius", 10), fill=bg)
    if style.get("shadow_opacity", 0) > 0:
        sh = _hex_to_rgb(style["shadow_color"]) + (int(255 * style["shadow_opacity"]),)
        d.multiline_text((tx + sx, ty + sy), wrapped, fill=sh, stroke_width=bold, **common)
    if outline > 0:
        edge = _hex_to_rgb(style["stroke_color"]) + (255,)
        d.multiline_text((tx, ty), wrapped, fill=edge, stroke_width=outline + bold, stroke_fill=edge, **common)
    fill = _hex_to_rgb(style["font_color"]) + (255,)
    d.multiline_text((tx, ty), wrapped, fill=fill, stroke_width=bold, stroke_fill=fill, **common)

    x = (W - bw) // 2
    y = H - style["bottom_offset"] - ty   # 保持"文字顶部≈H-bottom_offset"的旧定位
    return block, x, y


def render_preview_pil(frame_img, text, style):
    """实时预览：把紧凑字幕块贴到缓存帧上。"""
    base = frame_img.convert("RGBA")
    block, x, y = render_block(base.size, text, style)
    base.alpha_composite(block, (max(0, x), max(0, y)))
    return base.convert("RGB")


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


def _apply_partial(partial):
    """把一组样式字段并入当前样式并保存，然后重跑（供预设/颜色快捷按钮使用）。"""
    base = _load_style() or {}
    base.update(partial)
    st.session_state["subtitle_style"] = base
    _save_style(base)
    st.rerun()


def _list_fonts():
    """扫描 fonts/ 目录返回 {显示名: 路径}。"""
    fonts = {}
    if config.FONTS_DIR.exists():
        for p in sorted(config.FONTS_DIR.iterdir()):
            if p.suffix.lower() in (".ttf", ".ttc", ".otf"):
                fonts[p.name] = str(p)
    return fonts


def _draw_safe_area(img):
    """在预览图上叠加标题安全区（5% 边距）与水平中线参考线。"""
    img = img.copy()
    d = ImageDraw.Draw(img)
    w, h = img.size
    mx, my = int(w * 0.05), int(h * 0.05)
    d.rectangle([mx, my, w - mx, h - my], outline=(255, 255, 0), width=2)
    d.line([(w // 2, 0), (w // 2, h)], fill=(255, 0, 0), width=1)
    return img


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
            _lang_displays = list(config.LANG_OPTIONS.keys())
            _default_display = next((d for d, v in config.LANG_OPTIONS.items() if v == "English"), _lang_displays[0])
            preview_lang_display = st.selectbox(
                "预览语言", _lang_displays, index=_lang_displays.index(_default_display),
                help="预览文本会按所选语言显示，便于确认字体能否正确渲染该语言。",
            )
            preview_lang = config.LANG_OPTIONS[preview_lang_display]
            preview_video = st.file_uploader("选择一个视频用于字幕样式预览", type=["mp4", "mov", "mkv"])
            show_guides = st.checkbox("显示安全区参考线", value=False,
                                      help="黄框为标题安全区(5% 边距)，红线为水平中线，便于对齐。")
            if preview_video is not None:
                # 预览只需一帧：仅在「新上传」时解码一次，取帧后立即删除临时视频，
                # 后续每次拖动滑块都复用缓存帧，不再重复读写/解码整段视频。
                file_key = getattr(preview_video, "file_id", None) or (preview_video.name, preview_video.size)
                if st.session_state.get("preview_file_key") != file_key:
                    tmp = config.TEMP_DIR / "preview_frame_src"
                    try:
                        tmp.write_bytes(preview_video.getvalue())
                        with VideoFileClip(str(tmp)) as clip:
                            t = min(1.0, (clip.duration or 0) / 2)
                            st.session_state['preview_frame'] = Image.fromarray(clip.get_frame(t))
                            st.session_state['video_size'] = clip.size
                        st.session_state['preview_file_key'] = file_key
                    except Exception as e:
                        st.error(f"视频加载失败: {e}")
                        st.session_state.pop('preview_frame', None)
                        st.session_state.pop('preview_file_key', None)
                    finally:
                        tmp.unlink(missing_ok=True)

        with col2:
            st.subheader("⚙️ 样式参数")

            # 一键样式预设
            pc1, pc2 = st.columns([0.7, 0.3])
            chosen_preset = pc1.selectbox("样式预设", ["自定义"] + list(config.STYLE_PRESETS.keys()),
                                          label_visibility="collapsed")
            if pc2.button("应用", use_container_width=True) and chosen_preset != "自定义":
                _apply_partial(config.STYLE_PRESETS[chosen_preset])

            # 字体来源：上传 > fonts/ 目录 > 系统默认
            uploaded_font = st.file_uploader("上传自定义字体 (.ttf/.ttc/.otf)", type=["ttf", "ttc", "otf"])
            bundled = _list_fonts()
            font_choice = st.selectbox("字体", ["系统默认"] + list(bundled.keys()),
                                       help="把字体放进项目 fonts/ 目录即可在此选择；上传字体优先级最高。")
            if uploaded_font:
                font_path = str(config.TEMP_DIR / "uploaded_font.ttf")
                Path(font_path).write_bytes(uploaded_font.read())
                st.caption("当前使用：上传的字体")
            elif font_choice != "系统默认":
                font_path = bundled[font_choice]
            else:
                font_path = default_font_path
                st.caption(f"系统默认：`{Path(default_font_path).name if default_font_path else '未找到'}`"
                           "（拉丁语言适用；中日韩 / 泰 / 阿拉伯等请放字体到 fonts/ 或上传）")

            if 'video_size' in st.session_state and font_path:
                w, h = st.session_state['video_size']
                saved = _load_style() or {}

                with st.container(border=True):
                    st.markdown("**字体 / 字重 / 颜色**")
                    font_size = st.slider("字体大小", 12, 120, saved.get("font_size", 48))
                    bold = st.slider("加粗（字重）", 0, 6, saved.get("bold", 1),
                                     help="伪加粗：用同色描边把字身撑粗，任何字体都适用。")
                    font_color = st.color_picker("字体颜色", saved.get("font_color", "#FFFFFF"))
                    swatch = st.columns(len(config.COLOR_PRESETS))
                    for col, (name, (fc, sc)) in zip(swatch, config.COLOR_PRESETS.items()):
                        if col.button(name, use_container_width=True):
                            _apply_partial({"font_color": fc, "stroke_color": sc})
                with st.container(border=True):
                    st.markdown("**描边**")
                    stroke_width = st.slider("描边宽度", 0, 6, saved.get("stroke_width", 1))
                    stroke_color = st.color_picker("描边颜色", saved.get("stroke_color", "#000000"))
                with st.container(border=True):
                    st.markdown("**背景色块**")
                    bg_enabled = st.checkbox("启用半透明底条", saved.get("bg_enabled", False))
                    bg_color = st.color_picker("背景颜色", saved.get("bg_color", "#000000"))
                    bg_opacity = st.slider("背景不透明度", 0.0, 1.0, saved.get("bg_opacity", 0.5))
                    bg_padding = st.slider("背景内边距(px)", 0, 40, saved.get("bg_padding", 12))
                with st.container(border=True):
                    st.markdown("**位置与排版**")
                    bottom_offset = st.slider("距底部距离(px)", 0, h // 2, saved.get("bottom_offset", 80))
                    width_ratio = st.slider("最大宽度比例", 0.2, 1.0,
                                            round(saved.get("max_text_width", int(w * 0.8)) / w, 2), step=0.05)
                    line_spacing = st.slider("行距(px)", 0, 40, saved.get("line_spacing", max(2, int(font_size * 0.2))))
                    max_lines = st.slider("最多行数（0=不限，超出自动缩字）", 0, 4, saved.get("max_lines", 0))
                with st.expander("阴影"):
                    shadow_opacity = st.slider("阴影不透明度", 0.0, 1.0, saved.get("shadow_opacity", 0.5))
                    shadow_color = st.color_picker("阴影颜色", saved.get("shadow_color", "#000000"))
                    shadow_offset_y = st.slider("阴影垂直偏移(px)", -10, 10, saved.get("shadow_offset", (0, 2))[1])

                style = {
                    "font_path": str(font_path), "font_size": font_size, "bold": bold, "font_color": font_color,
                    "stroke_color": stroke_color, "stroke_width": stroke_width, "bottom_offset": bottom_offset,
                    "max_text_width": int(w * width_ratio), "shadow_color": shadow_color,
                    "shadow_opacity": shadow_opacity, "shadow_offset": (0, shadow_offset_y),
                    "bg_enabled": bg_enabled, "bg_color": bg_color, "bg_opacity": bg_opacity, "bg_padding": bg_padding,
                    "line_spacing": line_spacing, "max_lines": max_lines,
                }
                st.session_state["subtitle_style"] = style
                _save_style(style)
            elif not font_path:
                st.info("请先上传字体后再调整样式。")
            else:
                st.info("请先上传预览视频以加载样式参数。")

        if 'preview_frame' in st.session_state and 'subtitle_style' in st.session_state:
            with col1:
                style = st.session_state["subtitle_style"]
                # 按所选预览语言动态显示示例文本
                preview_text = config.PREVIEW_SAMPLES.get(preview_lang, config.PREVIEW_SAMPLES["English"])
                if preview_lang in config.NON_LATIN_LANGS and not uploaded_font:
                    st.info(f"「{preview_lang_display}」为非拉丁文字，默认 Arial 无法显示，"
                            "请在右侧上传对应字体后再预览。")
                try:
                    preview_img = render_preview_pil(st.session_state['preview_frame'], preview_text, style)
                    if show_guides:
                        preview_img = _draw_safe_area(preview_img)
                    st.image(preview_img, caption="字幕样式预览（实时；与最终烧录一致）")
                except Exception as e:
                    st.warning(f"⚠️ 预览渲染失败（通常是字体问题）：{e}\n"
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
            s_col1, s_col2, s_col3 = st.columns(3)
            with s_col1:
                match_mode = st.radio("SRT 匹配方式", ("按文件名匹配", "按顺序对应"))
            with s_col2:
                crf = st.select_slider("输出压缩质量", options=[18, 20, 23, 28], value=23,
                                       help="CRF值越低，质量越高体积越大。18高质量, 23均衡, 28小体积。")
            with s_col3:
                preset = st.selectbox("编码速度 (preset)", config.ENCODE_PRESETS,
                                      index=config.ENCODE_PRESETS.index(config.DEFAULT_PRESET),
                                      help="越靠后越慢、压缩率越高。medium 通常是速度与体积的良好平衡。")

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
                            str(output_path), codec="libx264", audio_codec="aac", preset=preset,
                            ffmpeg_params=["-crf", str(crf)], threads=4, logger=None
                        )
                        final_video.close()
                    log_container.success(f"✅ {video_name} 已处理完成（耗时 {time.time() - t0:.0f}s）。")
                except Exception as e:
                    log_container.error(f"❌ 处理 {video_name} 时出错: {e}")

            st.balloons()
            st.success("🎉 所有视频已处理完成！")
