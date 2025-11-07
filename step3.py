import streamlit as st
from pathlib import Path
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from PIL import Image
import pysrt
import os
import json

# ===================== 配置文件 =====================
CONFIG_FILE = "subtitle_config.json"

def load_config():
    default_config = {
        "font_path": r"C:\Windows\Fonts\arial.ttf" if os.name == "nt" else "Arial",
        "font_size": 66,
        "font_color": "#FFFFFF",
        "stroke_color": "#FFFFFF",
        "stroke_width": 1,
        "bottom_offset": 574,
        "width_ratio": 0.75,
        "shadow_color": "#000000",
        "shadow_opacity": 0.75,
        "shadow_offset_x": 3,
        "shadow_offset_y": 2,
        "video_dir": "",
        "srt_dir": "",
        "output_dir": "",
        "match_mode_index": 0,
        "crf_index": 1
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        default_config.update(config)
    return default_config

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# ===================== 工具函数 =====================
def srt_time_to_seconds(t):
    return t.hours * 3600 + t.minutes * 60 + t.seconds + t.milliseconds / 1000

def generate_subtitle_clips(subs, w, h, style):
    clips = []
    shadow_offset = (style["shadow_offset_x"], style["shadow_offset_y"])
    for sub in subs:
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

    # 加载持久化配置
    config = load_config()

    # ---------- Step 1: 样式预览 ----------
    st.subheader("🎨 Step 1: 字幕样式可视化调整")
    preview_video = st.file_uploader("选择一个视频用于字幕样式预览", type=["mp4", "mov", "mkv"])

    uploaded_font = st.sidebar.file_uploader("上传自定义字体 (.ttf)", type=["ttf"])
    if uploaded_font:
        font_path = Path("uploaded_font.ttf")
        with open(font_path, "wb") as f:
            f.write(uploaded_font.read())
        st.sidebar.success("✅ 自定义字体已加载")
        config["font_path"] = str(font_path)

    st.sidebar.header("🎨 字幕样式设置")
    config["font_size"] = st.sidebar.slider("字体大小", 12, 80, config["font_size"])
    config["font_color"] = st.sidebar.color_picker("字体颜色", config["font_color"])
    config["stroke_color"] = st.sidebar.color_picker("描边颜色", config["stroke_color"])
    config["stroke_width"] = st.sidebar.slider("描边宽度", 0, 5, config["stroke_width"])
    config["bottom_offset"] = st.sidebar.slider("字幕距离视频底部 (像素)", 0, 1000, config["bottom_offset"])
    config["width_ratio"] = st.sidebar.slider("字幕最大宽度占视频比例", 0.2, 1.0, config["width_ratio"], step=0.05)
    config["shadow_color"] = st.sidebar.color_picker("阴影颜色", config["shadow_color"])
    config["shadow_opacity"] = st.sidebar.slider("阴影透明度", 0.0, 1.0, config["shadow_opacity"], step=0.05)
    config["shadow_offset_x"] = st.sidebar.slider("阴影水平偏移 (像素)", -20, 20, config["shadow_offset_x"])
    config["shadow_offset_y"] = st.sidebar.slider("阴影垂直偏移 (像素)", -20, 20, config["shadow_offset_y"])

    if preview_video:
        temp_video_path = Path("temp_preview_video.mp4")
        with open(temp_video_path, "wb") as f:
            f.write(preview_video.read())
        clip = VideoFileClip(str(temp_video_path))
        w, h = clip.size
        style = config.copy()
        style["max_text_width"] = int(w * style["width_ratio"])

        shadow_clip = TextClip("I am subtitle", fontsize=style["font_size"] + 1, color=style["shadow_color"],
                               method="caption", size=(style["max_text_width"], None), align="center",
                               font=style["font_path"]).set_opacity(style["shadow_opacity"]).set_position(
            ("center", h - style["bottom_offset"] + style["shadow_offset_y"]))
        txt_clip = TextClip("I am subtitle", fontsize=style["font_size"], color=style["font_color"],
                            stroke_color=style["stroke_color"], stroke_width=style["stroke_width"],
                            method="caption", size=(style["max_text_width"], None), align="center",
                            font=style["font_path"]).set_position(("center", h - style["bottom_offset"]))
        preview_clip = CompositeVideoClip([clip.subclip(0, 5), shadow_clip, txt_clip])
        frame = preview_clip.get_frame(1.0)
        st.image(Image.fromarray(frame), caption="字幕样式预览")
        st.success("✅ 样式设置已保存，可用于批量字幕添加。")

    # ---------- Step 2: 批量加字幕 ----------
    st.subheader("📦 Step 2: 批量为视频添加字幕")
    config["video_dir"] = st.text_input("视频文件夹路径", config["video_dir"])
    config["srt_dir"] = st.text_input("SRT 文件夹路径", config["srt_dir"])
    config["output_dir"] = st.text_input("输出视频文件夹路径", config["output_dir"])

    match_mode_labels = ["按文件名匹配同名 SRT", "按排序顺序对应"]
    config["match_mode_index"] = st.radio("选择 SRT 匹配方式", match_mode_labels, index=config["match_mode_index"]) == match_mode_labels[0] and 0 or 1

    crf_options = {"高质量（CRF 18）": 18, "标准（CRF 20）": 20, "均衡（CRF 23）": 23, "小体积（CRF 28）": 28}
    crf_index = st.radio("选择压缩档位", list(crf_options.keys()), index=config["crf_index"])
    selected_crf = crf_options[crf_index]
    config["crf_index"] = list(crf_options.keys()).index(crf_index)

    if st.button("🚀 开始批量添加字幕"):
        save_config(config)  # 保存配置
        if not os.path.exists(config["video_dir"]) or not os.path.exists(config["srt_dir"]):
            st.warning("请提供有效的视频和 SRT 文件夹路径。")
            return

        video_files = sorted([f for f in os.listdir(config["video_dir"]) if f.lower().endswith((".mp4", ".mov", ".mkv"))])
        srt_files = sorted([f for f in os.listdir(config["srt_dir"]) if f.lower().endswith(".srt")])

        if not video_files or not srt_files:
            st.warning("视频或字幕文件夹为空。")
            return

        if config["match_mode_index"] == 1 and len(video_files) != len(srt_files):
            st.warning("⚠️ 视频文件数量与 SRT 文件数量不一致！")
            return

        Path(config["output_dir"]).mkdir(parents=True, exist_ok=True)
        progress = st.progress(0)
        total = len(video_files)

        for i, video_name in enumerate(video_files):
            video_path = os.path.join(config["video_dir"], video_name)
            srt_name = Path(video_name).stem + ".srt" if config["match_mode_index"] == 0 else srt_files[i]
            srt_path = os.path.join(config["srt_dir"], srt_name)
            output_path = os.path.join(config["output_dir"], video_name)

            if not os.path.exists(srt_path):
                st.warning(f"⚠️ {video_name} 没有找到对应的 SRT ({srt_name})，跳过")
                continue
            if os.path.exists(output_path):
                st.info(f"✅ {video_name} 已存在，跳过")
                continue

            clip = VideoFileClip(video_path)
            w, h = clip.size
            style = config.copy()
            style["max_text_width"] = int(w * style["width_ratio"])

            subs = pysrt.open(srt_path)
            subtitle_clips = generate_subtitle_clips(subs, w, h, style)
            video = CompositeVideoClip([clip, *subtitle_clips])
            st.write(f"🎞️ 正在处理: {video_name}（CRF={selected_crf}）")
            video.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                preset="slow",
                ffmpeg_params=["-crf", str(selected_crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
                threads=4,
                fps=clip.fps,
                logger=None
            )
            progress.progress((i + 1) / total)
            st.success(f"✅ {video_name} 已处理完成")
        st.success("🎉 所有视频已处理完成！")
        save_config(config)  # 再次保存配置

if __name__ == "__main__":
    run()