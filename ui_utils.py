"""通用 Streamlit UI 辅助。"""
import os
import streamlit as st


def validate_dir(path: str, exts=None, key: str = ""):
    """对文件夹路径做实时校验并就地给出反馈。

    返回匹配到的文件名列表（已排序）；路径无效时返回 None。
    exts 为 None 时只校验文件夹是否存在。
    """
    if not path:
        return None
    if not os.path.isdir(path):
        st.error("❌ 路径不存在或不是文件夹")
        return None
    if exts is None:
        st.success("✅ 文件夹有效")
        return []
    files = sorted(f for f in os.listdir(path) if f.lower().endswith(exts))
    if files:
        st.success(f"✅ 找到 {len(files)} 个匹配文件")
    else:
        st.warning("⚠️ 文件夹内未找到匹配文件")
    return files
