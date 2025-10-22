@echo off
REM -------------------------------
REM 项目根目录
SET PROJECT_DIR=%~dp0
cd /d %PROJECT_DIR%

REM -------------------------------
REM 检查是否存在 venv
IF NOT EXIST "venv" (
    echo "虚拟环境不存在，正在创建..."
    python -m venv venv
)

REM -------------------------------
REM 激活虚拟环境
call venv\Scripts\activate

REM -------------------------------
REM 安装依赖
echo "正在安装依赖..."
pip install --upgrade pip
pip install -r requirements.txt

REM -------------------------------
REM 启动 Streamlit
echo "启动 Streamlit..."
streamlit run main.py

pause