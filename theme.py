"""统一视觉层：全局 CSS、品牌头部、步骤进度条、页头。
让四个步骤呈现「一套工具」的一致观感。处理逻辑与此无关。"""
import streamlit as st

import config

PRIMARY = "#6C63FF"
GRADIENT = "linear-gradient(135deg, #6C63FF 0%, #8B7CF6 100%)"

# 四个步骤的元信息（顺序即流水线）
STEPS = [
    {"key": "step1", "no": "①", "icon": "📝", "name": "翻译", "title": "批量翻译 SRT",
     "desc": "使用 AI 批量翻译字幕，按语言分目录输出，并维护翻译记忆。"},
    {"key": "step2", "no": "②", "icon": "🔄", "name": "微调", "title": "单集重新翻译",
     "desc": "对单个文件重新翻译，做质量修正与细节优化。"},
    {"key": "step3", "no": "③", "icon": "🎨", "name": "字幕", "title": "批量添加字幕",
     "desc": "可视化设计字幕样式，并批量硬编码到视频中。"},
    {"key": "step4", "no": "④", "icon": "🗜️", "name": "压缩", "title": "批量压缩视频",
     "desc": "H.264 编码压缩视频，减小体积方便分发。"},
]


def inject_css():
    st.markdown(
        """
        <style>
        /* ---- 基础排版 ---- */
        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI',
                         'PingFang SC', 'Microsoft YaHei', sans-serif;
        }
        .block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1080px; }
        [data-testid="stHeader"] { background: transparent; }
        footer { visibility: hidden; }

        /* ---- 品牌头部 ---- */
        .lt-hero {
            display: flex; align-items: center; justify-content: space-between;
            padding: 4px 2px 18px 2px;
        }
        .lt-brand { display: flex; align-items: center; gap: 14px; }
        .lt-logo {
            font-size: 30px; width: 52px; height: 52px; border-radius: 14px;
            display: flex; align-items: center; justify-content: center;
            background: rgba(108,99,255,0.12);
        }
        .lt-title {
            font-size: 26px; font-weight: 800; letter-spacing: -.5px; line-height: 1.1;
            background: linear-gradient(135deg, #6C63FF, #B06CFF);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .lt-sub { font-size: 13px; opacity: .6; margin-top: 2px; }
        .lt-status {
            font-size: 13px; font-weight: 600; padding: 7px 14px; border-radius: 999px;
            white-space: nowrap;
        }
        .lt-ok  { color: #0f9d58; background: rgba(15,157,88,.12); }
        .lt-bad { color: #d93025; background: rgba(217,48,37,.12); }

        /* ---- 步骤进度条 ---- */
        .lt-step-no { font-size: 18px; font-weight: 700; }
        .lt-step-name { font-size: 13px; opacity: .85; }
        .lt-track { height: 4px; border-radius: 999px; background: rgba(108,99,255,.15);
                    margin: 2px 0 22px 0; overflow: hidden; }
        .lt-track > div { height: 100%; background: """ + GRADIENT + """; border-radius: 999px; }

        /* 把步骤导航按钮做成药丸节点 */
        div[data-testid="column"] .stButton > button {
            width: 100%; border-radius: 12px; font-weight: 600; padding: 10px 0;
            border: 1px solid rgba(108,99,255,.18);
        }

        /* ---- 通用按钮 ---- */
        .stButton > button {
            border-radius: 11px; font-weight: 600; transition: all .15s ease;
        }
        .stButton > button:hover {
            transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108,99,255,.22);
        }
        .stButton > button[kind="primary"] {
            background: """ + GRADIENT + """; border: none; color: #fff;
        }

        /* ---- 卡片化容器 ---- */
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 16px !important;
            border-color: rgba(108,99,255,.12) !important;
            box-shadow: 0 1px 3px rgba(16,24,40,.06);
        }

        /* ---- 页头 ---- */
        .lt-page-title { font-size: 21px; font-weight: 750; margin: 4px 0 2px; }
        .lt-page-desc  { font-size: 14px; opacity: .6; margin-bottom: 14px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header():
    """品牌栏 + API 状态。"""
    if config.get_api_key():
        status = '<div class="lt-status lt-ok">🟢 API 已连接</div>'
    else:
        status = '<div class="lt-status lt-bad">🔴 未检测到 API Key</div>'
    st.markdown(
        f"""
        <div class="lt-hero">
          <div class="lt-brand">
            <div class="lt-logo">🎬</div>
            <div>
              <div class="lt-title">LanTrans</div>
              <div class="lt-sub">视频翻译与字幕嵌入工具</div>
            </div>
          </div>
          {status}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stepper(active_key: str) -> str:
    """渲染可点击的步骤进度条，返回当前选中的步骤 key。"""
    active_idx = next(i for i, s in enumerate(STEPS) if s["key"] == active_key)
    cols = st.columns(len(STEPS))
    clicked = active_key
    for i, (col, step) in enumerate(zip(cols, STEPS)):
        with col:
            label = f"{step['no']} {step['icon']} {step['name']}"
            is_active = i == active_idx
            if st.button(label, key=f"nav_{step['key']}", use_container_width=True,
                         type="primary" if is_active else "secondary"):
                clicked = step["key"]
    # 进度轨道：已完成 + 当前
    pct = int((active_idx + 1) / len(STEPS) * 100)
    st.markdown(f'<div class="lt-track"><div style="width:{pct}%"></div></div>', unsafe_allow_html=True)
    return clicked


def page_header(step_key: str):
    """每个步骤页统一的标题区。"""
    step = next(s for s in STEPS if s["key"] == step_key)
    st.markdown(
        f'<div class="lt-page-title">{step["icon"]} {step["title"]}</div>'
        f'<div class="lt-page-desc">{step["desc"]}</div>',
        unsafe_allow_html=True,
    )
