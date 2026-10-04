<div align="center">

<img src="assets/logo.svg" alt="Signaldesk Logo" width="480" />

<br/>

### 📑 تصفح الدليل حسب اللغة / Language Navigation

| 🇸🇦 **النسخة الحالية: العربية (AR)** | 🌐 [**Switch to English Version (EN)**](README_EN.md) |
| :---: | :---: |
| ✅ *أنت تتصفح الدليل باللغة العربية* | 👉 [انقر هنا للانتقال إلى README_EN.md](README_EN.md) |

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
<strong>منظومة استخبارات مصادر مفتوحة (OSINT) متكاملة لرصد، تصنيف، وتحليل المحتوى الرقمي عبر منصات التواصل الاجتماعي والويب، مع كشف السلوك المنسق (CIB)، تتبع منشأ الأخبار (Patient Zero)، واستخراج النصوص عبر الـ OCR وتفريغ الصوت/الفيديو بالذكاء الاصطناعي.</strong>
</p>

[الميزات](#-الميزات-الرئيسية) • [التحديثات](#-أبرز-التحديثات-الحالية) • [المعمارية](#-معمارية-النظام) • [المتطلبات](#-المتطلبات-الأساسية) • [التنصيب والتشغيل](#-دليل-التنصيب-والتشغيل-خطوة-بخطوة) • [التنزيل والتثبيت والبناء](#-دليل-التنزيل-والتثبيت-والبناء-لويندوز) • [دليل التثبيت الكامل](INSTALLATION.md) • [دليل المستخدم الكامل](deployment/USER_GUIDE_AR.md) • [المعالج التلقائي](deployment/setup-wizard.ps1) • [إعداد الذكاء الاصطناعي](#-إعداد-مزودي-الذكاء-الاصطناعي) • [واجهات الـ API](#-توثيق-واجهات-البرمجة-api)

</div>

---

## 📖 جدول المحتويات
1. [نظرة عامة على المنظومة](#-نظرة-عامة)
2. [الميزات والقدرات الرئيسية](#-الميزات-الرئيسية)
3. [أبرز التحديثات الحالية](#-أبرز-التحديثات-الحالية)
4. [معمارية النظام ومخطط التدفق](#-معمارية-النظام)
5. [حزمة التقنيات المستخدمة (Tech Stack)](#-حزمة-التقنيات-المستخدمة)
6. [المتطلبات الأساسية (Prerequisites)](#-المتطلبات-الأساسية)
7. [دليل التنصيب والتشغيل خطوة بخطوة](#-دليل-التنصيب-والتشغيل-خطوة-بخطوة)
   - [أ. إعداد البيئة الخلفية (Backend Setup)](#1-إعداد-الخادم-الخلفي-backend)
   - [ب. إعداد قاعدة البيانات والترحيل (Database & Migrations)](#2-إعداد-قاعدة-البيانات-postgresql)
   - [ج. إعداد وتشغيل الواجهة الأمامية (Frontend Setup)](#3-إعداد-وتشغيل-الواجهة-الأمامية-frontend)
8. [التشغيل الدائم وأيقونة شريط المهام في Windows](#-التشغيل-الدائم-وأيقونة-شريط-المهام-في-windows)
9. [📥 التنزيل والتثبيت والبناء لويندوز](#-دليل-التنزيل-والتثبيت-والبناء-لويندوز)
10. [تحديث النسخة من GitHub](#-تحديث-النسخة-من-github)
11. [إعداد نماذج الذكاء الاصطناعي والـ OCR](#-إعداد-مزودي-الذكاء-الاصطناعي)
12. [الأدوار والصلاحيات (RBAC & Security)](#-الأدوار-والصلاحيات-rbac)
13. [هيكل المجلدات (Project Directory Structure)](#-هيكل-المشروع)
14. [توثيق واجهات البرمجة (API Documentation)](#-توثيق-واجهات-البرمجة-api)

---

## 🎯 نظرة عامة

منصة **Media Monitoring Platform (Signaldesk)** هي نظام دفاعي وتحليلي متقدم مصمم لغرف العمليات، مراكز الدراسات، والجهات الأمنية والإعلامية لرصد ومكافحة المحتوى الضار، خطابات العنف والكراهية، التهديدات، وتتبع الحملات الإعلامية المنسقة.

تتيح المنظومة تتبع المنشورات عبر مصادر متعددة وتجميعها تحت **مواضيع رصد مستقلة (Topics)**، وتحليلها آلياً بنماذج لغوية ضخمة (LLMs) تعمل **محلياً دون إنترنت (Air-gapped)** أو عبر **السحابة**، مع إمكانية استخراج النصوص العربية والإنجليزية من لقطات الشاشة والصور وتفريغ ملفات الفيديو.

---

## ✨ الميزات الرئيسية

### 🌐 1. الرصد متعدد المنصات (Multi-Platform Ingestion)
- **Telegram:** سحب مباشر من القنوات والمجموعات العامة والمغلقة باستخدام بروتوكول MTProto الأصلي (`Telethon`).
- **Facebook, Instagram, TikTok, Threads, X (Twitter):** تكامل هجين عبر `Meta Graph API` الرسمي مع مسار بديل مرن باستخدام محركات `Apify`.
- **Reddit & YouTube:** سحب المنشورات والتعليقات وتفريغ نصوص الفيديو (`YouTube Transcript API` & `yt-dlp`).
- **RSS / News Portals:** قراءة وتطهير تلقائي لخلاصات الأخبار والمواقع الإخبارية مع استخراج الصور المرفقة.

### 🧠 2. ذكاء اصطناعي هجين لتصنيف التهديدات (AI Threat Intelligence)
- **تعدد المزودين (Pluggable Providers):**
  - **Ollama (محلي بالكامل):** تشغيل نماذج مثل `Qwen 2.5 7B`، `LLaMA 3.1 8B`، أو `DeepSeek R1` لأقصى درجات سرية البيانات.
  - **Google AI Studio (Gemini 2.0 Flash / Pro):** للسرعة الفائقة والدقة العالية في التحليل المتعدد الوسائط.
  - **OpenRouter:** وصول مرن لمئات النماذج العالمية (`Claude 3.5 Sonnet`, `GPT-4o mini`).
- **تصنيف دقيق لمستويات الخطورة:** (منخفض `Low`، متوسط `Medium`، مرتفع `High`، حرج `Critical`).
- **10 فئات رصد للمحتوى:** (عنف جسدي، عنف نفسي، كراهية، تطرف، أسلحة، عصابات، إيذاء الذات، تحريض...).
- **تلخيص فوري باللغة العربية:** صياغة موجز استخباري لكل منشور خطير.

### 🖼️ 3. استخراج الوسائط المتعددة (Multimodal OCR & Audio/Video)
- **التعرف البصري على الحروف (OCR):** دعم استخراج النصوص العربية والإنجليزية من لقطات الشاشة المرفقة عبر `EasyOCR` و `Tesseract`.
- **التفريغ الصوتي (Speech-to-Text):** تفريغ مقاطع الصوت والفيديو محلياً باستخدام `faster-whisper`.
- **الرصد السريع (Quick Ingest):** إمكانية رفع لقطة شاشة، ملف وسائط، أو رابط مفرد للتحليل اللحظي المباشر.

### 🕸️ 4. رسم شبكات الانتشار وكشف السلوك المنسق (Propagation & CIB Graph)
- **تحديد "المريض صفر" (Patient Zero):** كشف أول حساب/مصدر أطلق الخبر أو الإشاعة عبر الشبكة.
- **تتبع خطوط النقل والتعزيز (Amplifiers):** قياس الفارق الزمني بالثواني والدقائق بين المصدر الأصلي ومن أعاد النشر.
- **كشف الحملات المنسقة (Coordinated Inauthentic Behavior - CIB):** خوارزمية ذكية لاكتشاف تكرار نفس البصمة النصية من مصادر متعددة في نوافذ زمنية محددة.

### 🏢 5. العزل الموضعي ونظام الصلاحيات (Topic Isolation & RBAC)
- **عزل كامل للبيانات:** كل موضوع رصد (`Topic`) مستقل بمصادره، كلماته المفتاحية، مستنداته، ومحلليه.
- **هيكل صلاحيات متدرج:** (`super_admin`, `topic_manager`, `analyst`, `observer`, `topic_admin`, `topic_monitor`).
- **دورة اعتماد المقترحات (Approvals Workflow):** تمكين المراقبين من اقتراح مصادر وكلمات تخضع لموافقة مدير الموضوع.
- **سجل تدقيق كامل (Audit Log):** توثيق كل عملية داخل المنصة بالوقت وهوية المستخدم وتفاصيل الحدث.

### 📄 6. تقارير تنفيذية وتنبيهات فورية (Reporting & Alerts)
- **توليد تقارير PDF تنفيذية:** تقارير إحصائية وتحليلية رسمية احترافية عبر مكتبة `ReportLab`.
- **محرك كشف القفزات المفاجئة (Spike Detection):** رصد الارتفاع المفاجئ في وتيرة النشر وتنبيه غرف العمليات.

## 🔄 أبرز التحديثات الحالية

- **تشغيل إنتاجي على Windows:** تثبيت Backend كخدمة Windows باسم `SignalDeskServer` عبر NSSM، مع التشغيل التلقائي بعد إعادة تشغيل الجهاز.
- **تحديث آمن من GitHub:** سكربت `deployment/update-from-github.ps1` يفحص التعديلات المحلية، يجلب آخر نسخة، يثبت الاعتماديات، يشغّل الاختبارات، يبني الواجهة، ثم يعيد تشغيل الخدمة مع فحص `/health`.
- **مراقبة من شريط المهام:** أداة `SignalDesk Monitor` تعرض حالة الخدمة وتوفر فتح النظام والسجلات، وبدء/إيقاف/إعادة التشغيل، ونسخ رابط الوصول من الشبكة المحلية.
- **خط تحليل AI محسّن:** دعم مزودين محليين وسحابيين، تحليل دفعي متزامن، حفظ نتائج التحليل والأخطاء لكل منشور، واستخدام سياق الموضوع ومحتوى المنشور في الطلب.
- **إدخال مصادر أوسع:** دعم Telegram وMeta وApify وReddit وYouTube وRSS/Atom، مع Quick Ingest للروابط والملفات والوسائط.
- **تكاملات خارجية:** مسارات Webhook لربط التنبيهات والبيانات بأدوات الأتمتة مثل n8n.
- **حماية وتشغيل أوضح:** عزل المواضيع، RBAC، سجل تدقيق، تحديد معدل الطلبات، وفحص صحة الخدمة مع ملفات سجلات مستقلة.

---

## 🏛️ معمارية النظام

```mermaid
flowchart TB
    subgraph Sources["📡 مصادر البيانات (Data Ingestion)"]
        TG["Telegram Channels"]
        FB["Facebook / Instagram"]
        RD["Reddit / YouTube"]
        TW["X (Twitter) / TikTok"]
        RSS["RSS Feeds & News"]
        QI["Quick Ingest (Uploads/URLs)"]
    end

    subgraph Orchestrator["⚙️ محرك المعالجة والسحب (FastAPI Backend)"]
        ScraperEngine["Scraper Orchestrator"]
        DedupEngine["Deduplication (MD5 Fingerprints)"]
        MediaExtractor["OCR (EasyOCR) & Whisper Audio"]
        AIAnalyzer["AI Service (Ollama / Gemini / OpenRouter)"]
        PropGraph["Network Propagation & CIB Engine"]
        AlertEngine["Spike & Threat Alerts"]
    end

    subgraph Storage["💾 طبقة البيانات والتخزين"]
        Postgres[(PostgreSQL DB)]
        StorageDir["Media & Knowledge Storage"]
    end

    subgraph Presentation["💻 واجهة المستخدم (Next.js SPA)"]
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

## 🛠️ حزمة التقنيات المستخدمة

| الطبقة | التقنية | الوصف والوظيفة |
| :--- | :--- | :--- |
| **Backend Framework** | `FastAPI 0.104+` | خادم API عالي السرعة مبني على Python الحديث و Async IO |
| **ORM & Database** | `SQLAlchemy 2.0` + `PostgreSQL` | إدارة وتخزين البيانات العلائقية ومحرك الاستعلامات |
| **Database Migrations** | `Alembic` | إدارة وتتبع ترقيات وتعديلات جداول قاعدة البيانات |
| **Frontend Framework** | `Next.js 16` + `React 19` | واجهة مستخدم تفاعلية (App Router) سريعة ومتقدمة |
| **UI & Styling** | `TailwindCSS v4` + `Lucide Icons` | تصميم احترافي، ثنائي اللغة (عربي/إنجليزي)، وداعم للوضع المظلم |
| **AI Providers** | `Ollama` / `Google GenAI` / `OpenRouter` | محركات الاستنتاج وتصنيف المخاطر والتلخيص الآلي |
| **Media & OCR** | `EasyOCR`, `PyTesseract`, `Faster-Whisper` | قراءة النصوص من الصور وتفريغ المحاضرات والمقاطع المرئية |
| **Social Scraping** | `Telethon`, `Apify Client`, `PRAW`, `yt-dlp` | محولات الربط وجلب البيانات من مختلف الشبكات |
| **PDF Generation** | `ReportLab` | توليد تقارير استخباراتية تنفيذية عالية الجودة |
| **Security & Auth** | `JWT (python-jose)`, `Bcrypt`, `SlowAPI` | المصادقة، التشفير، التحكم بالصلاحيات، وحماية الـ Rate Limit |

---

## 📋 المتطلبات الأساسية

تأكد من توفر الأدوات التالية على نظامك قبل البدء:
1. **Python:** الإصدار `3.10` أو `3.11` أو `3.12`.
2. **Node.js:** الإصدار `18.x` أو `20.x` مع مدير الحزم `npm` أو `pnpm`.
3. **PostgreSQL:** الإصدار `14` أو أحدث (يمكن تشغيله محلياً أو عبر Docker).
4. **(اختياري) Ollama:** في حال رغبتك بتشغيل الذكاء الاصطناعي محلياً دون اتصال خارجي.
5. **(اختياري) Tesseract-OCR:** لتحسين سرعة معالجة الصور (EasyOCR مدمج ويعمل تلقائياً بدونها).

---

## 🚀 دليل التنصيب والتشغيل خطوة بخطوة

### 1. استنساخ المستودع (Clone Repository)

```bash
git clone https://github.com/hosam76b/signaldesk.git
cd signaldesk
```

---

### 2. إعداد الخادم الخلفي (Backend)

#### الخيار السريع (لمستخدمي Windows):
يمكنك تشغيل ملف الإعداد التلقائي الذي يقوم بإنشاء البيئة الافتراضية وتثبيت كافة الحزم ومحركات Playwright:
```cmd
setup.bat
```

#### الخيار اليدوي (Linux / macOS / Windows PowerShell):

1. **إنشاء البيئة الافتراضية وتفعيلها:**
   ```bash
   # على Linux / macOS:
   python3 -m venv .venv
   source .venv/bin/activate

   # على Windows (PowerShell):
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **ترقية pip وتثبيت الاعتماديات:**
   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **تثبيت متصفحات Playwright للأتمتة:**
   ```bash
   playwright install chromium
   ```

---

### 3. إعداد قاعدة البيانات وتكوين ملف `.env`

1. **إنشاء قاعدة بيانات في PostgreSQL:**
   ```sql
   CREATE DATABASE media_monitor;
   ```

2. **نسخ وتجهيز ملف المتغيرات البيئية:**
   قم بإنشاء ملف `.env` في المجلد الرئيسي بناءً على المثال:
   ```bash
   # على Linux / macOS:
   cp .env.example .env

   # على Windows (PowerShell / CMD):
   copy .env.example .env
   ```

3. **تعديل قيم `.env` الأساسية:**
   ```env
   # إعدادات التطبيق
   APP_NAME="Signaldesk Monitoring Platform"
   DEBUG=true
   LOG_LEVEL=INFO

   # رابط قاعدة البيانات PostgreSQL (قم بتعديل كلمة المرور واسم المستخدم)
   DB_URL=postgresql://postgres:password@localhost:5432/media_monitor

   # مفتاح التشفير للأمان (قم بتغييره في بيئة الإنتاج)
   SECRET_KEY=change-this-to-a-secure-random-secret-key-32-chars

   # دورية السحب التلقائي (بالثواني)
   SCRAPING_ENABLED=true
   SCRAPING_INTERVAL_SECONDS=300

   # إعدادات مزود الذكاء الاصطناعي (ollama / google_ai_studio / openrouter / custom_openai)
   AI_PROVIDER=ollama
   AI_MODEL=qwen2.5:7b
   OLLAMA_BASE_URL=http://localhost:11434

   # مفاتيح المزودين السحابيين (في حال استخدامها)
   GOOGLE_AI_STUDIO_API_KEY=your_gemini_api_key_here
   OPENROUTER_API_KEY=your_openrouter_api_key_here
   CUSTOM_OPENAI_BASE_URL=https://api.openai.com/v1
   CUSTOM_OPENAI_API_KEY=your_custom_provider_key_here

   # مفاتيح المنصات الاجتماعية (اختياري حسب الحاجة)
   APIFY_API_TOKEN=your_apify_token_here
   TELEGRAM_API_ID=your_telegram_api_id
   TELEGRAM_API_HASH=your_telegram_api_hash
   REDDIT_CLIENT_ID=your_reddit_client_id
   REDDIT_CLIENT_SECRET=your_reddit_client_secret
   YOUTUBE_API_KEY=your_youtube_api_key
   ```

4. **تطبيق ترحيلات قاعدة البيانات وحقن الحساب الافتراضي:**
   ```bash
   # تطبيق الترحيلات عبر Alembic
   alembic upgrade head

   # (اختياري) حقن بيانات تجريبية وحساب المسؤول الافتراضي
   python seed.py
   ```

5. **تشغيل خادم الـ Backend (FastAPI):**
   ```bash
   python main.py
   # أو عبر uvicorn مباشرة:
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```
   > 🌐 الخادم الخلفي سيعمل على: `http://localhost:8000`  
   > 📚 وثائق Swagger التفاعلية: `http://localhost:8000/docs`
   > 🧩 يمكن تصدير OpenAPI عبر: `python export_openapi.py --output openapi.json`

---

### 4. إعداد وتشغيل الواجهة الأمامية (Frontend)

1. **الانتقال لمجلد الواجهة:**
   ```bash
   cd frontend
   ```

2. **تثبيت حزم الـ Node.js:**
   ```bash
   npm install
   ```

3. **(اختياري) ضبط رابط الـ API:**
   بشكل افتراضي، تتصل الواجهة بـ `http://127.0.0.1:8000`. لتغييره، يمكنك إنشاء ملف `.env.local` داخل مجلد `frontend`:
   ```env
   NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
   ```

4. **تشغيل خادم التطوير للواجهة:**
   ```bash
   npm run dev
   ```
   > 🖥️ افتح المتصفح على الرابط: **`http://localhost:3000`**

---

## 🪟 التشغيل الدائم وأيقونة شريط المهام في Windows

هذا هو المسار الموصى به لجهاز Windows الذي يجب أن يبقى SignalDesk يعمل عليه بعد تسجيل الخروج أو إعادة التشغيل.

### تثبيت الخدمة

افتح **PowerShell بصلاحية مسؤول** من مجلد المشروع، ثم نفذ:

```powershell
Set-Location "C:\Users\Hosam\Documents\SignalDesk"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\deployment\install-service.ps1
```

يقوم المثبت تلقائيًا بإنشاء `.venv` عند الحاجة، تثبيت متطلبات Python، بناء الواجهة، تثبيت خدمة `SignalDeskServer` على المنفذ `8000`، إضافة قاعدة جدار الحماية، وإنشاء اختصار `SignalDesk.lnk` على سطح المكتب يفتح الواجهة على `http://127.0.0.1:8000`.

### 🔎 أداة المراقبة في شريط المهام (اختيارية)

أداة `SignalDesk Monitor` اختيارية وتُشغَّل يدويًا من مجلد المشروع:

```powershell
wscript.exe .\deployment\start_tray.vbs
```

> ⚠️ **تتطلب Python على جهازك:** الأداة تعمل عبر `.venv\Scripts\python.exe` ولا تُنشأ لها اختصارات تلقائية anymore لأن حزمة التثبيت لا تحزّم Python. عند تشغيلها ستظهر في منطقة الإشعارات بجانب الساعة؛ إن كانت مخفية افتح سهم **إظهار الأيقونات المخفية**.

توفر قائمة النقر الخيارات التالية:

- فتح SignalDesk على `http://127.0.0.1:8000`.
- بدء الخدمة أو إيقافها أو إعادة تشغيلها.
- فتح مجلد `logs`.
- نسخ رابط الوصول من أجهزة الشبكة المحلية.
- إغلاق أداة المراقبة فقط، دون إيقاف الخدمة.

للتحقق من حالة الخدمة وصحة الخادم:

```powershell
Get-Service SignalDeskServer
Invoke-RestMethod http://127.0.0.1:8000/health
```

يجب أن تكون حالة الخدمة `Running` وأن يعيد الفحص قيمة `healthy`. عند فشل أوامر التحكم من قائمة الأيقونة، شغّل أداة المراقبة أو PowerShell بصلاحية مسؤول.

### التشغيل اليدوي للتجربة

للتجربة دون تثبيت خدمة Windows:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

ثم افتح `http://127.0.0.1:8000`. أوقف الخادم التجريبي باستخدام `Ctrl+C`.

### تغيير منفذ الخدمة (مصدر واحد للمنفذ)

منفذ الاستماع والفحص الذاتي كانا إعدادين منفصلين، وأي اختلاف بينهما كان يجعل
الفحص الذاتي يعلن موت حلقة `accept` ويغلق خدمة سليمة. اليوم المنفذ معرَّف في
مكان واحد: `SIGNALDESK_PORT` في بيئة الخدمة، يقرأه `config.py` في `settings.port`،
وتمرره `main.py` إلى `self_check.start(port=...)`، بينما `uvicorn` يستمع لنفس القيمة
عبر `--port`. لتغيير المنفذ:

```powershell
# PowerShell بصلاحية مسؤول
.\deployment\set-service-port.ps1 -Port 8000
# للاستماع على هذا الجهاز فقط بدل شبكة محلية:
.\deployment\set-service-port.ps1 -Port 8000 -HostAddress 127.0.0.1
```

السكربت يتحقق أولاً من أن `SIGNALDESK_PORT` في `.env` يطابق المنفذ المطلوب، ثم
يحدّث الخدمة ويعيد تشغيلها، ثم يؤكد أن `/health` يعيد `healthy` وأن سطر
`Socket self-check started` يطابق المنفذ. إذا ظهر تحذير
`differs from SELF_CHECK_PORT` في السجل فالقيمتان ما زالت متعارضتين: صحّح
`SELF_CHECK_PORT` في `.env` ليطابق المنفذ الفعلي.

## 📥 التنزيل والتثبيت والبناء لويندوز

> 📖 **[الدليل الكامل التفصيلي: INSTALLATION.md](INSTALLATION.md)** — يغطي التنزيل والإعداد والبناء والتثبيت خطوة بخطوة.

### بناء حزمة التثبيت `SignalDesk_Setup.exe`

**المتطلبات:** Windows 10/11 أو Server 2016+ (64-bit) · Python 3.11+ · Node.js 18/20 · [Inno Setup 6.7.3](https://jrsoftware.org/isinfo.php) · [Apify Token](https://console.apify.com) (لمحرك الكشط).

```powershell
# 1) استنساخ المستودع
git clone https://github.com/hosam76b/signaldesk.git
cd signaldesk

# 2) اعتمادات Python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3) بناء الواجهة (يُنتج frontend\out)
cd frontend; npm install; npm run build; cd ..

# 4) متغيرات البيئة (Apify Token وغيرها)
copy .env.example .env
```

ثم شغّل البناء:

```powershell
# تلقائياً (يكتشف Inno Setup من المسارات القياسية)
.\deployment\build_installer.ps1

# أو بتحديد مسار المحرّك يدوياً
.\deployment\build_installer.ps1 -InnoPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

📦 **ناتج البناء:** `releases\SignalDesk_Setup.exe` بحجم **~2.6 ميجابايت**.

### تثبيت النظام (للمستخدم النهائي)

شغّل `SignalDesk_Setup.exe` **برتبة مسؤول (Administrator)**، ثم يقوم المُثبِّت تلقائياً بـ:

1. إنشاء بيئة Python داخل مجلد التثبيت وتثبيت الاعتماديات.
2. تسجيل خدمة Windows باسم **`SignalDeskServer`** تعمل تلقائياً عند بدء الجهاز على المنفذ `8000`.
3. إضافة قاعدة جدار حماية للسماح بالدخول على المنفذ `8000`.
4. إنشاء اختصار **سطح المكتب** و**قائمة ابدأ** يفتح الواجهة على [http://127.0.0.1:8000](http://127.0.0.1:8000).

### التحكم بالخدمة

```powershell
Get-Service  SignalDeskServer            # الحالة
Start-Service SignalDeskServer           # تشغيل
Stop-Service  SignalDeskServer           # إيقاف
Restart-Service SignalDeskServer         # إعادة تشغيل
Invoke-RestMethod http://127.0.0.1:8000/health   # فحص الصحة
```

أو عبر واجهة الخدمات: `Win + R` ثم `services.msc` ← زر الفأرة الأيمن على `SignalDeskServer` ← Start / Stop / Restart.

### إزالة التثبيت (Clean Uninstall)

`Settings → Apps → Installed apps → SignalDesk → Uninstall`، أو يدوياً بصلاحية مسؤول:

```powershell
.\deployment\uninstall-service.ps1
```

يُزال تلقائياً: **خدمة `SignalDeskServer`** · **قاعدة جدار الحماية** · **الاختصارات** · **مجلد التثبيت كاملاً**. احفظ أي بيانات تريد الاحتفاظ بها قبل الإزالة.

---

## 🔁 تحديث النسخة من GitHub

بعد تثبيت الخدمة، استخدم سكربت التحديث الرسمي من **PowerShell بصلاحية مسؤول**:

```powershell
Set-Location "C:\Users\Hosam\Documents\SignalDesk"
.\deployment\update-from-github.ps1
```

يتحقق السكربت أولًا من عدم وجود تعديلات محلية، ثم ينفذ بالترتيب:

1. جلب آخر نسخة من فرع `main` ودمجها بطريقة Fast-forward فقط.
2. تحديث متطلبات Python.
3. تشغيل جميع اختبارات Backend عبر `pytest`.
4. تثبيت حزم الواجهة وبناء نسخة الإنتاج.
5. إعادة تشغيل `SignalDeskServer` والتحقق من `/health`.

إذا كانت لديك تعديلات محلية، احفظها في Commit أو استخدم Stash قبل التحديث. لا ترفع ملفات الأسرار أو البيانات التشغيلية إلى GitHub، ومنها `.env` و`media_monitor.db` ومجلد `media_uploads`.

لإعادة تشغيل الخدمة فقط بعد تعديل الكود أو `.env`:

```powershell
.\deployment\restart-service.ps1
```

لإزالة الخدمة مع الإبقاء على قاعدة البيانات والمنشورات:

```powershell
.\deployment\uninstall-service.ps1
```

لمزيد من التفاصيل التشغيلية راجع [دليل تشغيل Windows](deployment/USER_GUIDE_AR.md) و[دليل النشر](docs/DEPLOYMENT_CHECKLIST_STEP4.md).

---

## 🤖 إعداد مزودي الذكاء الاصطناعي

تدعم المنصة 3 خيارات للمحركات اللغوية؛ يمكنك التبديل بينها مباشرة من واجهة النظام (`إعدادات النظام / System Settings`) أو عبر ملف `.env`:

### الخيار 1: التشغيل المحلي بالكامل عبر Ollama (مستحسن للخصوصية)
1. قم بتنزيل وتثبيت [Ollama](https://ollama.com/).
2. شغّل النموذج المطلوب في الطرفية:
   ```bash
   ollama pull qwen2.5:7b
   # أو
   ollama pull llama3.1:8b
   ```
3. ستقوم المنصة تلقائياً باكتشاف خادم Ollama والاتصال به على `http://localhost:11434`.

### الخيار 2: Google Gemini (Google AI Studio)
1. احصل على مفتاح مجاني من [Google AI Studio](https://aistudio.google.com/).
2. عيّن `AI_PROVIDER=google_ai_studio` وضع مفتاحك في `GOOGLE_AI_STUDIO_API_KEY`.
3. النموذج الافتراضي الموصى به: `gemini-2.0-flash`.

### الخيار 3: OpenRouter
1. عيّن `AI_PROVIDER=openrouter` وضع مفتاحك في `OPENROUTER_API_KEY`.
2. النموذج الافتراضي: `openai/gpt-4o-mini` أو `anthropic/claude-3.5-sonnet`.

---

## 👥 الأدوار والصلاحيات (RBAC)

تعتمد المنظومة نظام صلاحيات متدرج يضمن عزل المهام وحماية البيانات:

| الدور (Role) | الصلاحيات والمسؤوليات |
| :--- | :--- |
| **Super Admin** | صلاحيات كاملة: إدارة المستخدمين، إنشاء وحذف المواضيع، تكوين مزودي الذكاء الاصطناعي وسجلات التدقيق. |
| **Topic Manager / Admin** | إدارة موضوع محدد: إضافة واعتماد المصادر والكلمات المفتاحية، إدارة المحللين المخصصين للموضوع. |
| **Analyst** | تحليل المنشورات، تعديل تقييم المخاطر، استخراج التقارير، وتوليد الرسوم البيانية لانتشار المحتوى. |
| **Observer / Monitor** | قراءة المحتوى وتقديم مقترحات مصادر وكلمات جديدة (تخضع لموافقة مدير الموضوع) واستخدام الـ Quick Ingest. |

### 🔑 الحساب الافتراضي بعد التثبيت (Default Admin):
- **البريد الإلكتروني:** `admin@example.com`
- **كلمة المرور:** `admin123`
*(⚠️ تنبيه أمني: يرجى تغيير كلمة المرور فور تسجيل الدخول الأول من صفحة الملف الشخصي).*

---

## 📂 هيكل المشروع

```text
signaldesk/
├── app/                        # النواة الخلفية (FastAPI Application)
│   ├── api/                    # مسارات ومتحكمات الـ REST API
│   │   ├── auth.py             # تسجيل الدخول والرموز المميزة (JWT)
│   │   ├── topics.py           # إدارة المواضيع والمصادر والكلمات المفتاحية
│   │   ├── posts.py            # استعراض وتحديث وتصنيف المنشورات
│   │   ├── ai_analysis.py      # عمليات التحليل والتقييم بالذكاء الاصطناعي
│   │   ├── analytics.py        # تحليلات الانتشار والرسوم البيانية CIB
│   │   ├── ingestion.py        # الرصد اللحظي السريع Quick Ingest
│   │   ├── approvals.py        # نظام اعتماد ومراجعة المقترحات
│   │   ├── audit.py            # سجل التدقيق والأنشطة
│   │   ├── knowledge.py        # إدارة مستودع المستندات المعرفية
│   │   └── data_export.py      # تصدير البيانات والتقارير التنفيذية PDF
│   ├── core/                   # الأمان، التشفير، الصلاحيات والـ Rate Limiting
│   ├── db/                     # جلسات SQLAlchemy ونماذج التهيئة
│   ├── models/                 # جداول ونماذج قاعدة البيانات (ORM Models)
│   └── services/               # منطق الأعمال والمحركات المساعدة
│       ├── ai_service.py       # محول الذكاء الاصطناعي (Ollama/Gemini/OpenRouter)
│       ├── scraper_orchestrator.py # منسق عمليات السحب والتجميع
│       ├── scraper_service.py  # محولات المنصات (RSS, Meta, Apify, Telegram)
│       ├── media_extraction_service.py # محرك استخراج OCR و Whisper
│       ├── propagation_service.py # محرك شبكة الانتشار و Patient Zero
│       ├── pdf_report_service.py  # محرك بناء تقارير الـ PDF
│       └── alerts.py           # محرك كشف القفزات والإنذارات
├── frontend/                   # الواجهة الأمامية (Next.js 16 App Router)
│   └── src/app/                # صفحات ومكونات واجهة المستخدم
├── migrations/                 # ملفات ترحيل قاعدة البيانات (Alembic)
├── tests/                      # الاختبارات الأوتوماتيكية الشاملة (Pytest)
├── config.py                   # إعدادات Pydantic المركزية
├── main.py                     # نقطة انطلاق خادم الـ Backend
├── seed.py                     # سكريبت زرع البيانات التجريبية
├── setup.bat                   # سكريبت التنصيب التلقائي لأنظمة Windows
└── requirements.txt            # مكتبات Python المطلوبة
```

---

## 📡 توثيق واجهات البرمجة (API Documentation)

لشرح الاستخدام والتحكم بشكل مستقل راجع: [API_USAGE.md](docs/API_USAGE.md)

يوفر خادم FastAPI توثيقاً تفاعلياً حياً لجميع المسارات:
- **Swagger UI:** `http://localhost:8000/docs` (يتيح تجربة الـ Endpoints مباشرة مع تضمين Bearer Token).
- **ReDoc:** `http://localhost:8000/redoc` (عرض مفصل وموثق للمطورين).
- **OpenAPI JSON:** `http://localhost:8000/openapi.json` أو عبر الأمر `python export_openapi.py --output openapi.json`.

يمكن التحكم في روابط التوثيق والإخراج من ملف `.env` باستخدام:
- `API_DOCS_ENABLED=false` لإخفاء Swagger و ReDoc مع إبقاء OpenAPI متاحاً.
- `API_OPENAPI_ENABLED=false` لإيقاف Swagger و ReDoc وملف OpenAPI من الخادم.
- `API_DOCS_URL`, `API_REDOC_URL`, `API_OPENAPI_URL` لتغيير المسارات الافتراضية.
- `CORS_ALLOW_ORIGINS` لتحديد واجهات Frontend المسموح لها بالاتصال، مفصولة بفواصل.

### أبرز المسارات (Key API Endpoints):
- `POST /api/auth/login`: مصادقة المستخدمين وتوليد JWT Token.
- `GET /api/v1/topics`: جلب المواضيع المتاحة للمستخدم بحسب صلاحياته.
- `POST /api/v1/ingestion/quick-url`: إدخال رابط مفرد للتحليل اللحظي الفوري.
- `POST /api/v1/ingestion/quick-upload`: رفع صورة/مقطع فيديو لتشغيل الـ OCR وتفريغ الصوت وتصنيف المحتوى.
- `GET /api/v1/analytics/topics/{id}/propagation-graph`: جلب شبكة انتشار المحتوى وحسابات التضخيم.
- `GET /api/v1/topics/{id}/executive-pdf`: تنزيل التقرير التنفيذي الرسمي بصيغة PDF.
- `POST /api/ai/analyze-pending`: تشغيل دورة التقييم بالذكاء الاصطناعي على المنشورات الجديدة.

---

## 🧪 تشغيل الاختبارات (Running Tests)

للتأكد من سلامة الكود وجميع المحولات والوحدات:

```bash
# تشغيل كامل حزمة الاختبارات
pytest

# تشغيل اختبارات التحقق من الصلاحيات و الـ RBAC
python test_phase2_rbac.py

# تشغيل اختبارات محولات سحب البيانات
python test_phase3_ingestion.py
```

---

## 🔒 إرشادات الأمان والإنتاج (Production Best Practices)

1. **تغيير مفتاح `SECRET_KEY`:** تأكد من وضع مفتاح عشوائي مشفر لا يقل عن 32 حرفاً في بيئة الإنتاج.
2. **عزل خوادم الـ Inference:** عند معالجة أحجام ضخمة من الصور والصوتيات، يفضل تشغيل Ollama أو Whisper على خادم مزود ببطاقات GPU مخصصة.
3. **تفعيل شهادات HTTPS:** استخدم خادم وسيط (مثل Nginx أو Caddy) لتأمين حركة المرور وتوفير شهادات SSL/TLS.
4. **تأمين مفاتيح الـ API:** لا تقم برفع ملف `.env` إلى مستودعات Git العامة نهائياً.

---

## 📄 الترخيص (License)

هذا المشروع متاح للاستخدام والتطوير الداخلي وفق شروط رخصة [MIT License](LICENSE).

<div align="center">
<b>تم تطوير المنظومة لدعم الرصد الذكي، حماية الفضاء الرقمي، والتحليل الاستخباري الدقيق للأحداث.</b>
</div>

