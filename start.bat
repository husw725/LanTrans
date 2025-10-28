@echo off
REM -------------------------------
REM 项目根目录
SET PROJECT_DIR=%~dp0
cd /d %PROJECT_DIR%

REM -------------------------------
REM 检查是否存在 venv
IF NOT EXIST "venv" (
    echo "Venv not found, creating one..."
    python -m venv venv
)

REM -------------------------------
REM 激活虚拟环境
call venv\Scripts\activate

REM -------------------------------
REM 安装依赖
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

REM -------------------------------
REM 启动 Streamlit
echo "Starting Streamlit..."
streamlit run main.py

pause