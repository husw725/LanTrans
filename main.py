import streamlit as st
import importlib

st.sidebar.title("选择步骤")
step = st.sidebar.radio("Step", ["Step 1: 批量翻译 SRT", "Step 2: 单集重新翻译", "Step 3: 批量添加字幕"])

if step == "Step 1: 批量翻译 SRT":
    from step1 import run
    run()

elif step == "Step 2: 单集重新翻译":
    from step2 import run
    run()

elif step == "Step 3: 批量添加字幕":
    from step3 import run   
    run()