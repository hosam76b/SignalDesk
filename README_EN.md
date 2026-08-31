<div align="center">

<img src="assets/logo.svg" alt="Signaldesk Logo" width="480" />

<br/>

### 📑 Language Navigation / تصفح الدليل حسب اللغة

| 🌐 **Current: English Version (EN)** | 🇸🇦 [**التبديل إلى النسخة العربية (AR)**](README.md) |
| :---: | :---: |
| ✅ *You are viewing the English documentation* | 👉 [Click here to switch to README.md](README.md) |

<br/>

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14%2B-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-v4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_AI-white?style=for-the-badge&logo=ollama&logoColor=black)](https://ollama.com/)
[![Google Gemini](https://img.shields.io/badge/Google_Gemini-2.0_Flash-8E75C2?style=for-the-badge&logo=googlegemini&logoColor=white)](https://aistudio.google.com/)

<p align="center">
<strong>An enterprise-grade Open Source Intelligence (OSINT) and threat monitoring platform for ingesting, classifying, and analyzing digital content across social networks and the web. Features Coordinated Inauthentic Behavior (CIB) detection, origin tracking (Patient Zero), OCR image text extraction, and AI-powered audio/video transcription.</strong>
</p>

[Features](#-key-features) • [Architecture](#-system-architecture) • [Prerequisites](#-prerequisites) • [Installation & Setup](#-step-by-step-installation--setup) • [AI Configuration](#-ai-provider-configuration) • [API Documentation](#-api-documentation)

</div>

---

## 📖 Table of Contents
1. [System Overview](#-system-overview)
2. [Key Features](#-key-features)
3. [System Architecture & Flow](#-system-architecture)
4. [Tech Stack](#-tech-stack)
5. [Prerequisites](#-prerequisites)
6. [Step-by-Step Installation & Setup](#-step-by-step-installation--setup)
   - [1. Backend Setup](#1-backend-setup)
   - [2. Database & Migrations](#2-database-setup-postgresql)
   - [3. Frontend Setup](#3-frontend-setup-nextjs-16)
7. [AI Provider Configuration](#-ai-provider-configuration)
8. [Roles & Permissions (RBAC)](#-roles--permissions-rbac)
9. [Project Directory Structure](#-project-directory-structure)
10. [API Documentation](#-api-documentation)
11. [Testing & Verification](#-running-tests)
12. [Security & Production Best Practices](#-security--production-best-practices)

---

## 🎯 System Overview

**Signaldesk (Media Monitoring Platform)** is an advanced defensive and intelligence platform engineered for operation centers, strategic research units, and security/media organizations. It actively detects harmful content, violence, extremism, weapons, and disinformation campaigns while mapping viral propagation patterns.

The platform organizes monitoring activities into isolated **Topics**, ingesting content through automated schedulers or direct uploads. Ingested data is enriched via local or cloud LLMs, OCR engines, and speech recognition models, providing real-time intelligence feeds, executive PDF reports, and interactive network graphs.

---

## ✨ Key Features

### 🌐 1. Multi-Platform Data Ingestion
- **Telegram:** Native channel and group scraping (public and private) via MTProto protocol (`Telethon`).
- **Facebook, Instagram, TikTok, Threads, X (Twitter):** Hybrid architecture supporting the official `Meta Graph API` with automatic fallback to distributed `Apify` actors.
- **Reddit & YouTube:** Automated post/comment ingestion and video dialogue extraction (`YouTube Transcript API` & `yt-dlp`).
- **RSS & News Portals:** Ingestion and XML sanitation for major news agencies and RSS/Atom feeds.

### 🧠 2. Hybrid AI Threat Intelligence
- **Pluggable AI Providers:**
  - **Ollama (Fully Local & Offline):** Run models like `Qwen 2.5 7B`, `LLaMA 3.1 8B`, or `DeepSeek R1` on-premise for sensitive, air-gapped deployments.
  - **Google AI Studio (Gemini 2.0 Flash / Pro):** High-speed multimodal understanding and reasoning.
  - **OpenRouter:** Dynamic access to `Claude 3.5 Sonnet`, `GPT-4o mini`, and more.
- **Severity Scoring:** Automated classification into `Low`, `Medium`, `High`, and `Critical`.
- **10 Monitored Threat Categories:** Physical violence, psychological violence, hate speech, extremism, weapons, gangs, self-harm, incitement, and more.
- **Automated Intelligence Summaries:** Executive analytical briefs generated in clear Arabic or English.

### 🖼️ 3. Multimodal Media Processing (OCR & Whisper)
- **Optical Character Recognition (OCR):** Local Arabic and English text extraction from images and screenshots using `EasyOCR` and `Tesseract`.
- **Audio & Video Transcription:** Local speech-to-text transcription powered by `faster-whisper`.
- **Quick Ingest:** Immediate one-off analysis for single URLs, screenshots, and media files without altering scheduled scrapers.

### 🕸️ 4. Network Propagation & CIB Detection
- **Patient Zero Identification:** Pinpoint the exact original source or account that published a story or claim.
- **Amplifier Tracking:** Calculate propagation delays (in seconds/minutes) across secondary spreaders.
- **Coordinated Inauthentic Behavior (CIB):** Heuristic clustering algorithms detect identical content footprints posted across disparate channels within defined timeframes.

### 🏢 5. Topic Isolation & Enterprise RBAC
- **Multi-Tenant Topic Architecture:** Strict data isolation per topic (sources, keywords, knowledge documents, posts, and analysts).
- **Granular Roles:** `super_admin`, `topic_manager`, `analyst`, `observer`, `topic_admin`, and `topic_monitor`.
- **Approval Workflow:** Observers can propose keywords and sources requiring topic manager approval before ingestion.
- **Comprehensive Audit Trail:** Immutable audit logs recording all user actions, evaluations, and exports.

### 📄 6. Executive PDF Reporting & Incident Alerts
- **Executive PDF Generation:** Formal, formatted intelligence reports built with `ReportLab`.
- **Spike Detection Engine:** Statistical volume spike monitoring triggering instant alerts for unusual narrative surges.

---

## 🏛️ System Architecture

```mermaid
flowchart TB
    subgraph Sources["📡 Data Ingestion Layer"]
        TG["Telegram Channels"]
        FB["Facebook / Instagram"]
        RD["Reddit / YouTube"]
        TW["X (Twitter) / TikTok"]
        RSS["RSS Feeds & News"]
        QI["Quick Ingest (Uploads/URLs)"]
    end

    subgraph Orchestrator["⚙️ Processing & AI Pipeline (FastAPI Backend)"]
        ScraperEngine["Scraper Orchestrator"]
        DedupEngine["Deduplication (MD5 Fingerprints)"]
        MediaExtractor["OCR (EasyOCR) & Whisper Audio"]
        AIAnalyzer["AI Service (Ollama / Gemini / OpenRouter)"]
        PropGraph["Network Propagation & CIB Engine"]
        AlertEngine["Spike & Threat Alerts"]
    end

    subgraph Storage["💾 Storage & Persistence"]
        Postgres[(PostgreSQL DB)]
        StorageDir["Media & Knowledge Storage"]
    end

    subgraph Presentation["💻 Presentation Layer (Next.js SPA)"]
        FeedView["Live Intelligence Feed"]
        GraphView["Interactive Propagation Graph"]
        TopicHub["Topic & Resource Management"]
        AuditView["Security & Audit Trail"]
        ExportView["Executive PDF Reports"]
    end

    Sources --> ScraperEngine
    ScraperEngine --> DedupEngine
    DedupEngine --> MediaExtractor
    MediaExtractor --> AIAnalyzer
    AIAnalyzer --> Postgres
    MediaExtractor --> StorageDir
    Postgres --> PropGraph
    Postgres --> AlertEngine
    Postgres --> Presentation
```

---

## 🛠️ Tech Stack

| Layer | Technology | Details & Role |
| :--- | :--- | :--- |
| **Backend Framework** | `FastAPI 0.104+` | Async high-performance Python web API |
| **ORM & Database** | `SQLAlchemy 2.0` + `PostgreSQL 14+` | Relational data persistence & transactional integrity |
| **Migrations** | `Alembic` | Versioned schema migration management |
| **Frontend Framework** | `Next.js 16` + `React 19` | Modern Single Page Application with App Router |
| **UI Styling** | `TailwindCSS v4` + `Lucide Icons` | Responsive, bilingual (RTL/LTR), Dark/Light theme |
| **AI Engines** | `Ollama` / `Google GenAI` / `OpenRouter` | Multimodal threat classification and summarization |
| **OCR & Speech** | `EasyOCR`, `PyTesseract`, `Faster-Whisper` | Local computer vision and audio transcription |
| **Scraping Adapters** | `Telethon`, `Apify Client`, `PRAW`, `yt-dlp` | Social media and news feed collection |
| **PDF Reporting** | `ReportLab` | Automated executive intelligence dossier generator |
| **Security** | `JWT (python-jose)`, `Bcrypt`, `SlowAPI` | Token auth, rate limiting, and RBAC enforcement |

---

## 📋 Prerequisites

Ensure the following tools are installed on your environment:
1. **Python:** Version `3.10`, `3.11`, or `3.12`.
2. **Node.js:** Version `18.x` or `20.x` with `npm` or `pnpm`.
3. **PostgreSQL:** Version `14` or higher.
4. **(Optional) Ollama:** For on-premise/offline AI inference.
5. **(Optional) Tesseract-OCR:** For accelerated OCR processing (pure-Python EasyOCR is bundled as fallback).

---

## 🚀 Step-by-Step Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/hosam76b/signaldesk.git
cd signaldesk
```

---

### 2. Backend Setup

#### Quick Setup (Windows):
Execute the automated setup script to provision the virtual environment, install dependencies, and setup Playwright:
```cmd
setup.bat
```

#### Manual Setup (Linux / macOS / Windows PowerShell):

1. **Create and activate virtual environment:**
   ```bash
   # On Linux / macOS:
   python3 -m venv .venv
   source .venv/bin/activate

   # On Windows (PowerShell):
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Upgrade pip and install dependencies:**
   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Install Playwright browser binaries:**
   ```bash
   playwright install chromium
   ```

---

### 3. Database Setup (PostgreSQL)

1. **Create a PostgreSQL database:**
   ```sql
   CREATE DATABASE media_monitor;
   ```

2. **Configure environment variables (`.env`):**
   Copy the example environment template:
   ```bash
   # On Linux / macOS:
   cp .env.example .env

   # On Windows:
   copy .env.example .env
   ```

3. **Update `.env` values:**
   ```env
   APP_NAME="Signaldesk Monitoring Platform"
   DEBUG=true
   LOG_LEVEL=INFO

   # PostgreSQL Connection String
   DB_URL=postgresql://postgres:your_password@localhost:5432/media_monitor

   # JWT Security Secret (Use a strong random key in production)
   SECRET_KEY=change-this-to-a-secure-random-secret-key-32-chars

   # Scraping Scheduler Interval (in seconds)
   SCRAPING_ENABLED=true
   SCRAPING_INTERVAL_SECONDS=300

   # AI Provider: ollama | google_ai_studio | openrouter
   AI_PROVIDER=ollama
   AI_MODEL=qwen2.5:7b
   OLLAMA_BASE_URL=http://localhost:11434

   # Cloud AI Keys (if using cloud providers)
   GOOGLE_AI_STUDIO_API_KEY=your_gemini_api_key_here
   OPENROUTER_API_KEY=your_openrouter_api_key_here

   # Social Scraper Credentials (optional, as needed)
   APIFY_API_TOKEN=your_apify_token_here
   TELEGRAM_API_ID=your_telegram_api_id
   TELEGRAM_API_HASH=your_telegram_api_hash
   REDDIT_CLIENT_ID=your_reddit_client_id
   REDDIT_CLIENT_SECRET=your_reddit_client_secret
   YOUTUBE_API_KEY=your_youtube_api_key
   ```

4. **Run database migrations and seed default data:**
   ```bash
   # Apply Alembic schema migrations
   alembic upgrade head

   # Seed default admin and sample data
   python seed.py
   ```

5. **Start the FastAPI Backend:**
   ```bash
   python main.py
   # Or via uvicorn directly:
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```
   > 🌐 Backend API URL: `http://localhost:8000`  
   > 📚 Interactive Swagger Docs: `http://localhost:8000/docs`

---

### 4. Frontend Setup (Next.js 16)

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install Node.js dependencies:**
   ```bash
   npm install
   ```

3. **(Optional) Configure API endpoint:**
   The frontend defaults to `http://127.0.0.1:8000`. You can configure a custom URL in `frontend/.env.local`:
   ```env
   NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
   ```

4. **Launch development server:**
   ```bash
   npm run dev
   ```
   > 🖥️ Open your browser at: **`http://localhost:3000`**

---

## 🤖 AI Provider Configuration

The platform allows live switching between AI providers from the web UI (`System Settings`) or `.env`:

### Option 1: Local Ollama (Recommended for Privacy & Air-gapped)
1. Download and install [Ollama](https://ollama.com/).
2. Pull your preferred model:
   ```bash
   ollama pull qwen2.5:7b
   # or
   ollama pull llama3.1:8b
   ```
3. The platform connects automatically to `http://localhost:11434`.

### Option 2: Google Gemini (Google AI Studio)
1. Obtain an API key from [Google AI Studio](https://aistudio.google.com/).
2. Set `AI_PROVIDER=google_ai_studio` and supply `GOOGLE_AI_STUDIO_API_KEY`.
3. Recommended model: `gemini-2.0-flash`.

### Option 3: OpenRouter
1. Set `AI_PROVIDER=openrouter` and supply `OPENROUTER_API_KEY`.
2. Recommended models: `openai/gpt-4o-mini` or `anthropic/claude-3.5-sonnet`.

---

## 👥 Roles & Permissions (RBAC)

| Role | Permissions & Scope |
| :--- | :--- |
| **Super Admin** | Full access: user management, global topic creation, AI engine configuration, audit logs. |
| **Topic Manager / Admin** | Manages assigned topics: approve/reject proposed sources and keywords, manage topic analysts. |
| **Analyst** | Evaluates posts, edits threat severity, exports executive reports, analyzes propagation graphs. |
| **Observer / Monitor** | Read-only access with proposal capabilities (submit source/keyword suggestions) and Quick Ingest. |

### 🔑 Default Credentials:
- **Email:** `admin@example.com`
- **Password:** `admin123`
*(⚠️ Security notice: Change the default password immediately after first login in Profile Settings).*

---

## 📂 Project Directory Structure

```text
signaldesk/
├── app/                        # FastAPI Backend Application
│   ├── api/                    # REST API Route Controllers
│   │   ├── auth.py             # Authentication & JWT tokens
│   │   ├── topics.py           # Topic, source & keyword management
│   │   ├── posts.py            # Post review & classification endpoints
│   │   ├── ai_analysis.py      # LLM inference & threat evaluation
│   │   ├── analytics.py        # Propagation graphs & CIB analysis
│   │   ├── ingestion.py        # Global Quick Ingest (OCR/Uploads)
│   │   ├── approvals.py        # Proposal & approval workflows
│   │   ├── audit.py            # Immutable audit logging
│   │   ├── knowledge.py        # Contextual knowledge document repository
│   │   └── data_export.py      # PDF & CSV data export endpoints
│   ├── core/                   # Security, JWT, RBAC & SlowAPI rate limiting
│   ├── db/                     # SQLAlchemy session & database initialization
│   ├── models/                 # SQLAlchemy ORM database models
│   └── services/               # Core business logic & external integrations
│       ├── ai_service.py       # Pluggable AI engine (Ollama/Gemini/OpenRouter)
│       ├── scraper_orchestrator.py # Multi-platform ingestion coordinator
│       ├── scraper_service.py  # Platform adapters (RSS, Meta, Apify, Telegram)
│       ├── media_extraction_service.py # OCR & Whisper transcription pipeline
│       ├── propagation_service.py # Propagation graph & Patient Zero detection
│       ├── pdf_report_service.py  # ReportLab executive dossier generator
│       └── alerts.py           # Real-time narrative spike & threat alerts
├── frontend/                   # Next.js 16 (App Router) Frontend
│   └── src/app/                # React 19 pages, dashboards & components
├── migrations/                 # Alembic database migrations
├── tests/                      # Pytest automated test suites
├── config.py                   # Pydantic Settings configuration
├── main.py                     # Application entry point & startup lifespans
├── seed.py                     # Database seeder
├── setup.bat                   # Automated Windows installation script
└── requirements.txt            # Python dependencies
```

---

## 📡 API Documentation

FastAPI serves interactive API documentation out of the box:
- **Swagger UI:** `http://localhost:8000/docs` (interactive test client with JWT bearer support).
- **ReDoc:** `http://localhost:8000/redoc` (structured developer documentation).

### Core API Endpoints:
- `POST /api/auth/login`: Authenticate and obtain JWT access token.
- `GET /api/v1/topics`: List accessible monitoring topics.
- `POST /api/v1/ingestion/quick-url`: Ingest and analyze a single URL immediately.
- `POST /api/v1/ingestion/quick-upload`: Ingest image/video file, execute OCR/Whisper, and evaluate threat.
- `GET /api/v1/analytics/topics/{id}/propagation-graph`: Retrieve propagation graph, Patient Zero, and CIB clusters.
- `GET /api/v1/topics/{id}/executive-pdf`: Generate and download formal executive intelligence PDF.
- `POST /api/ai/analyze-pending`: Trigger batch AI evaluation on pending posts.

---

## 🧪 Running Tests

Verify all adapters, authentication, and analysis workflows:

```bash
# Run full unit and integration test suite
pytest

# Test RBAC and topic permission isolation
python test_phase2_rbac.py

# Test ingestion and scraper adapters
python test_phase3_ingestion.py
```

---

## 🔒 Security & Production Best Practices

1. **Rotate `SECRET_KEY`:** Generate a cryptographically secure 32+ character key before deploying to production.
2. **GPU Acceleration:** For high-throughput video transcription and OCR, run Whisper and EasyOCR on GPU-accelerated instances.
3. **HTTPS & Reverse Proxy:** Place the backend behind a reverse proxy (e.g., Nginx, Caddy, or Cloudflare) with valid SSL/TLS certificates.
4. **Environment Protection:** Never commit `.env` containing live secrets to public repositories.

---

## 📄 License

Distributed under the [MIT License](LICENSE).

<div align="center">
<b>Engineered for digital safety, intelligence analysis, and rapid response.</b>
</div>

