# Media Monitoring Platform - Windows Setup Guide

## Quick Start (Using batch file)

Simply run the batch file from the project root directory:

```batch
setup.bat
```

This will automatically:
1. Create a Python virtual environment
2. Activate the virtual environment
3. Upgrade pip
4. Install all dependencies from `requirements.txt`
5. Install Playwright browsers for web automation

---

## Manual Setup (Using PowerShell)

If you prefer to set up manually or troubleshoot, follow these PowerShell commands:

### 1. Verify Python Installation

```powershell
python --version
pip --version
```

If Python is not installed, download from: https://www.python.org/

### 2. Create Virtual Environment

```powershell
# Create venv folder (if it doesn't exist)
python -m venv venv

# Verify venv was created
Get-ChildItem venv
```

### 3. Activate Virtual Environment

```powershell
# For PowerShell
.\venv\Scripts\Activate.ps1

# If you get an execution policy error, run:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then try activating again:
.\venv\Scripts\Activate.ps1
```

**Note:** Your prompt should now show `(venv)` prefix, indicating the virtual environment is active.

### 4. Upgrade pip (Recommended)

```powershell
python -m pip install --upgrade pip
```

### 5. Install Dependencies

```powershell
pip install -r requirements.txt
```

Expected output:
```
Collecting fastapi==0.104.1
...
Successfully installed fastapi uvicorn sqlalchemy psycopg2-binary ... [18+ packages]
```

### 6. Install Playwright Browsers

```powershell
python -m playwright install
```

This installs Chromium, Firefox, and WebKit browsers for web automation.

---

## Configuration

### 1. Update .env File

Edit the `.env` file in the project root with your actual credentials:

```env
# Database (PostgreSQL)
DB_URL=postgresql://user:password@localhost:5432/media_monitor

# Redis
REDIS_URL=redis://127.0.0.1:6379/0

# JWT Settings (change SECRET_KEY in production!)
SECRET_KEY=your-secret-key-change-this-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# External APIs
AI_PROVIDER=google_ai_studio
AI_MODEL=gemini-2.0-flash
GOOGLE_AI_STUDIO_BASE_URL=https://generativelanguage.googleapis.com/v1beta/models
GOOGLE_AI_STUDIO_API_KEY=your-gemini-api-key
REDDIT_CLIENT_ID=your-reddit-client-id
REDDIT_CLIENT_SECRET=your-reddit-client-secret
REDDIT_USER_AGENT=MediaMonitor/1.0
YOUTUBE_API_KEY=your-youtube-api-key
```

Supported AI providers:

| Provider | `AI_PROVIDER` value | Base URL | API key variable |
|----------|---------------------|----------|------------------|
| Local Ollama | `ollama` | `http://localhost:11434` | Not required |
| Google AI Studio | `google_ai_studio` | `https://generativelanguage.googleapis.com/v1beta/models` | `GOOGLE_AI_STUDIO_API_KEY` |
| OpenRouter | `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| Custom OpenAI-compatible provider | `custom_openai` | Provider-specific `/v1` URL | `CUSTOM_OPENAI_API_KEY` if required |

For a custom provider such as LM Studio, vLLM, LiteLLM, or a private gateway, use `AI_PROVIDER=custom_openai`, set `CUSTOM_OPENAI_BASE_URL` to the provider's `/v1` endpoint, and set `CUSTOM_OPENAI_MODEL` to the model name exposed by that provider.

### 2. (Optional) Set Up PostgreSQL Database

```powershell
# If you have PostgreSQL installed, create the database:
# psql -U postgres
# CREATE DATABASE media_monitor;

# Or use Azure Database, AWS RDS, etc.
```

### 3. (Optional) Set Up Redis

```powershell
# Download Redis from: https://github.com/microsoftarchive/redis/releases
# Or use Windows Subsystem for Linux (WSL2):
# wsl --install Ubuntu
# wsl ubuntu install
# sudo apt install redis-server
# redis-server
```

---

## Running the Application

### Start the Application

```powershell
# Make sure virtual environment is activated
python main.py
```

Output should show:
```
🚀 Media Monitoring Platform v1.0.0 starting up...
Debug mode: True
Log level: INFO
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Access the API

- **Swagger UI (Interactive API Docs)**: http://localhost:8000/docs
- **ReDoc (Alternative Docs)**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

### Test Authentication

#### Login Endpoint
```powershell
# PowerShell
$response = Invoke-RestMethod -Uri "http://localhost:8000/api/auth/login" `
  -Method Post `
  -Headers @{"Content-Type"="application/json"} `
  -Body @{username="admin"; password="admin123"} | ConvertTo-Json

Write-Host $response
```

Or using curl:
```powershell
curl -X POST "http://localhost:8000/api/auth/login" `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","password":"admin123"}'
```

#### Default Test Credentials

| Role      | Username | Password    |
|-----------|----------|-------------|
| Admin     | admin    | admin123    |
| Analyst   | analyst  | analyst123  |

#### Get Current User
```powershell
# After login, use the access_token
$token = "your-access-token-here"

Invoke-RestMethod -Uri "http://localhost:8000/api/auth/me" `
  -Method Get `
  -Headers @{"Authorization"="Bearer $token"}
```

---

## Deactivate Virtual Environment

When you're done working, deactivate the virtual environment:

```powershell
deactivate
```

---

## Troubleshooting

### Issue: "python: The term 'python' is not recognized"

**Solution:** Python is not in your system PATH. Either:
- Reinstall Python and check "Add Python to PATH" during installation
- Use full path: `C:\Python311\python.exe` (adjust version as needed)
- Use `python3` instead of `python`

### Issue: "ExecutionPolicy" error when activating venv

**Solution:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\venv\Scripts\Activate.ps1
```

### Issue: "No module named 'fastapi'" after installation

**Solution:** Make sure virtual environment is activated (should show `(venv)` in prompt)

### Issue: PostgreSQL connection errors

**Solution:**
1. Check if PostgreSQL is running
2. Verify connection string in .env
3. Create database: `CREATE DATABASE media_monitor;`
4. Test connection with: `psycopg2-binary` or use a tool like pgAdmin

### Issue: Playwright browsers won't install

**Solution:**
```powershell
# Install dependencies first (may require admin)
python -m pip install playwright
python -m playwright install
```

---

## Project Structure

```
SignalDesk/
├── app/
│   ├── api/              # API route handlers
│   │   ├── auth.py       # Authentication endpoints
│   │   └── users.py      # User management endpoints
│   ├── core/
│   │   ├── security.py   # JWT & password hashing
│   │   └── __init__.py
│   ├── db/               # Database connections
│   ├── models/           # SQLAlchemy models
│   ├── services/         # Business logic
│   ├── workers/          # Celery background tasks
│   └── __init__.py
├── static/               # Static files (CSS, JS, images)
├── reports/              # Generated monitoring reports
├── venv/                 # Virtual environment (created after setup)
├── .env                  # Environment variables (gitignored)
├── config.py             # Configuration management
├── main.py               # FastAPI application entry point
├── requirements.txt      # Python dependencies
└── setup.bat             # Windows batch setup script
```

---

## Next Steps

1. ✅ Set up virtual environment and install dependencies
2. 📝 Update `.env` with actual API credentials
3. 🗄️ Set up PostgreSQL database
4. 🚀 Start the application: `python main.py`
5. 🧪 Test endpoints in Swagger UI: http://localhost:8000/docs
6. 📦 Develop additional features in `app/` directories

---

## Additional Resources

- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **SQLAlchemy ORM**: https://docs.sqlalchemy.org/
- **Pydantic**: https://docs.pydantic.dev/
- **Uvicorn**: https://www.uvicorn.org/
- **Python-Jose (JWT)**: https://python-jose.readthedocs.io/
- **Passlib (Hashing)**: https://passlib.readthedocs.io/

---

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review error messages carefully
3. Check application logs in the console
4. Visit the linked documentation resources

**Happy coding! 🚀**
