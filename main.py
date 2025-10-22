import streamlit as st
import importlib

st.sidebar.title("选择步骤")
step = st.sidebar.radio("Step", ["Step 1: 批量翻译 SRT", "Step 2: 单集重新翻译"])

if step == "Step 1: 批量翻译 SRT":
    import step1
    importlib.reload(step1)  # 确保修改后可即时生效

elif step == "Step 2: 单集重新翻译":
    import step2
    importlib.reload(step2)