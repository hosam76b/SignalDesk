@echo off
REM ============================================================================
REM Windows Setup Script for Media Monitoring Platform
REM ============================================================================
REM This script sets up the Python virtual environment and installs dependencies
REM Run this from the project root directory: facebook-monitor/
REM ============================================================================

echo.
echo ============================================================================
echo Media Monitoring Platform - Windows Setup
echo ============================================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

echo [1/5] Python version:
python --version
echo.

REM Create virtual environment
echo [2/5] Creating virtual environment...
if exist venv (
    echo Virtual environment already exists. Skipping creation.
) else (
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created successfully.
)
echo.

REM Activate virtual environment
echo [3/5] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)
echo Virtual environment activated.
echo.

REM Upgrade pip
echo [4/5] Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo WARNING: pip upgrade had issues, but continuing...
)
echo.

REM Install requirements
echo [5/5] Installing Python dependencies from requirements.txt...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo All dependencies installed successfully.
echo.

REM Install Playwright browsers
echo [BONUS] Installing Playwright browsers...
python -m playwright install
if errorlevel 1 (
    echo WARNING: Playwright installation had issues
)
echo.

echo ============================================================================
echo Setup Complete!
echo ============================================================================
echo.
echo Next steps:
echo 1. Update .env file with your actual credentials:
echo    - DB_URL: PostgreSQL connection string
echo    - GEMINI_API_KEY: Your Google Gemini API key
echo    - REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET: Reddit OAuth credentials
echo    - YOUTUBE_API_KEY: Your YouTube API key
echo.
echo 2. Run the application:
echo    python main.py
echo.
echo 3. Access the API:
echo    - Swagger UI: http://localhost:8000/docs
echo    - ReDoc: http://localhost:8000/redoc
echo.
echo 4. Default test credentials:
echo    - Username: admin / Password: admin123 (Admin role)
echo    - Username: analyst / Password: analyst123 (Analyst role)
echo.
echo To deactivate virtual environment later, run: deactivate
echo.
pause
