# 📥 دليل التنزيل والإعداد والبناء والتثبيت | Installation & Build Guide

<div align="center">

**SignalDesk — Media Monitoring Platform**
دليل شامل: من استنساخ المستودع إلى تشغيل النظام كخدمة Windows إنتاجية.

</div>

---

## 📑 جدول المحتويات

1. [المتطلبات الأساسية (Prerequisites)](#1-المتطلبات-الأساسية-prerequisites)
2. [إعداد بيئة التطوير والبناء (Build Setup Steps)](#2-إعداد-بيئة-التطوير-والبناء-build-setup-steps)
3. [إنشاء حزمة التثبيت SignalDesk_Setup.exe](#3-إنشاء-حزمة-التثبت-signaldesk_setupexe)
4. [دليل المستخدم النهائي للتثبيت (End-User Installation Guide)](#4-دليل-المستخدم-النهائي-للتثبيت-end-user-installation-guide)
5. [التحكم بالخدمة (Service Control)](#5-التحكم-بالخدمة-service-control)
6. [إزالة التثبيت (Clean Uninstall)](#6-إزالة-التثبيت-clean-uninstall)
7. [استكشاف الأخطاء وحلولها (Troubleshooting)](#7-استكشاف-الأخطاء-وحلولها-troubleshooting)

---

## 1. المتطلبات الأساسية (Prerequisites)

### متطلبات نظام التشغيل

| المتطلب | التفاصيل |
| :--- | :--- |
| **نظام التشغيل** | Windows 10 / 11 / Windows Server 2016+ (64-bit) |
| **المعالج** | 64-bit (x64) —غير مدعوم على معالجات 32-bit |
| **الذاكرة** | 4 GB كحد أدنى (8 GB مُستحسن مع محركات AI محلية) |
| **القرص** | 2 GB مساحة خالية على الأقل |
| **المنفذ** | `8000` (TCP Inbound) — يجب أن يكون متاحاً وغير محجوب |

> ⚠️ **ملاحظة:** النظام مصمم حصرياً لمنصة Windows. التشغيل على Linux أو macOS متاح للتطوير فقط عبر Backend، بينما حزمة التثبيت `.exe` غير مدعومة هناك.

### المتطلبات البرمجية

| الأداة | الإصدار | الغرض | ملاحظات |
| :--- | :--- | :--- | :--- |
| **Python** | `3.11` أو `3.12` | تشغيل الخادم (FastAPI) | يمكن الاعتماد على البيئة المضمنة `.venv` التي ينشئها المثبّت تلقائياً |
| **Node.js** | `18.x` أو `20.x` | بناء واجهة المستخدم | مطلوب **للمطوّر فقط** — الحزمة النهائية تحتوي `frontend/out` جاهزاً |
| **Inno Setup** | `6.7.3` | بناء حزمة التثبيت | [https://jrsoftware.org/isinfo.php](https://jrsoftware.org/isinfo.php) |
| **PostgreSQL** | `14` أو أحدث | قاعدة البيانات | مطلوب على جهاز التثبيت النهائي (يُنشئه `install-service.ps1`) |
| **Git** | أحدث إصدار | استنساخ المستودع | مستودع عام، لا يحتاج حساب |

### روابط تنزيل الأدوات

| الأداة | رابط التنزيل المباشر |
| :--- | :--- |
| **Inno Setup 6.7.3** | [https://jrsoftware.org/isinfo.php](https://jrsoftware.org/isinfo.php) |
| **Python 3.11+** | [https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/) |
| **Node.js LTS** | [https://nodejs.org/en/download](https://nodejs.org/en/download) |
| **PostgreSQL 14+** | [https://www.postgresql.org/download/windows/](https://www.postgresql.org/download/windows/) |
| **Git for Windows** | [https://git-scm.com/download/win](https://git-scm.com/download/win) |

### Apify Token (مطلوب لكشط شبكات التواصل)

تستخدم المنصة محرك **Apify** كمحرك سحب احتياطي لمصادر Facebook و Instagram و X و TikTok و Threads. للحصول على الرمز:

1. أنشئ حساباً مجانياً في [https://console.apify.com](https://console.apify.com).
2. من **Settings → Integrations → API Tokens** أنشئ رمزاً جديداً (Token).
3. انسخ الرمز ثم ضعه في ملف `.env`:

```env
APIFY_API_TOKEN=apify_api_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# معرّفات الـ Actors (اختيارية حسب المنصة المطلوبة)
APIFY_FACEBOOK_ACTOR_ID=your_facebook_actor_id
APIFY_INSTAGRAM_ACTOR_ID=your_instagram_actor_id
APIFY_X_ACTOR_ID=your_x_actor_id
APIFY_TIKTOK_ACTOR_ID=your_tiktok_actor_id
APIFY_THREADS_ACTOR_ID=your_threads_actor_id

# مدخلات الـ Actor القابلة للتخصيص (JSON) — مثال:
APIFY_FACEBOOK_ACTOR_INPUT={"startUrls":[{"url":"https://facebook.com/page"}]}
```

> 🔑 **بخصوص `APIFY_FACEBOOK_ACTOR_INPUT`:** يقبل حقل JSON يُمرَّر كـ `input` للـ Actor عند تشغيله (داخله `{url}` و`{max_items}`). استخدم `APIFY_API_TOKEN` مع `APIFY_MAX_ITEMS_PER_RUN` للتحكم في عدد النتائج المُعادة لكل دورة سحب.
>
> ℹ️ بدون هذا الرمز تعمل المنظومة بكامل وظائفها عبر المسارات الرسمية (Meta Graph API، Telethon، RSS) ولا يتأثر محرك Apify فقط.

---

## 2. إعداد بيئة التطوير والبناء (Build Setup Steps)

### الخطوة 1 — تنزيل وتثبيت Inno Setup 6.7.3

ثبّت Inno Setup من الرابط أعلاه. المسار القياسي على أنظمة Windows 64-bit:

```text
C:\Program Files (x86)\Inno Setup 6\ISCC.exe
```

> ملاحظة: يُثبَّت مُترجِم Inno Setup (`ISCC.exe`) افتراضياً مع Inno Setup 6. تأكد من وجوده قبل البناء في الخطوة 3.

### الخطوة 2 — استنساخ المستودع (Clone Repository)

```bash
git clone https://github.com/hosam76b/signaldesk.git
cd signaldesk
```

### الخطوة 3 — تثبيت الاعتماديات (Python)

المشروع يعتمد `pip` (ملف `requirements.txt`). الخيار الموصى به باستخدام بيئة افتراضية معزولة:

```bash
# إنشاء البيئة الافتراضية
python -m venv .venv

# تفعيلها (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# تثبيت الاعتماديات
python -m pip install --upgrade pip
pip install -r requirements.txt

# (اختياري) متطلبات التطوير والاختبارات
pip install -r requirements-dev.txt
```

> 💡 **بديل باستخدام `uv` (أسرع بكثير):**
> ```bash
> pip install uv
> uv venv                      # ينشئ .venv
> uv pip install -r requirements.txt
> ```

> على PowerShell إذا ظهر خطأ تنفيذ السكربت:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
> ```

### الخطوة 4 — بناء واجهة المستخدم (Frontend)

```bash
cd frontend
npm install
npm run build
```

يُنتج أمر `next build` مجلد **التصدير الثابت** التالي عبر `next.config.ts`:

```text
frontend/out/          ← يُقدَّم مباشرة بواسطة الخادم على http://127.0.0.1:8000
```

> 🔹 **لماذا `out` وليس `.next`؟** لأن `main.py` يخدم الواجهة من `frontend/out` (تصدير ثابت خفيف لا يحتاج Node على خادم الإنتاج). مجلد `.next` ملفات بناء وسيطة لا يحتاجها الإنتاج ويُستثنى من الحزمة.

### الخطوة 5 — ضبط متغيرات البيئة في `.env`

انسخ ملف المثال ثم عدّل القيم:

```powershell
# على Windows PowerShell
copy .env.example .env
```

أضف/عدّل هذه القيم الأساسية:

```env
# إعدادات التطبيق
APP_NAME="SignalDesk Monitoring Platform"
DEBUG=false
LOG_LEVEL=INFO

# رابط قاعدة البيانات
DB_URL=postgresql://postgres:password@localhost:5432/media_monitor

# مفتاح تشفير آمن (32+ حرفاً) — غيّره في الإنتاج
SECRET_KEY=change-this-to-a-secure-random-secret-key-32-chars

# محرك الكشط ومفتاح Apify
SCRAPING_ENABLED=true
SCRAPING_INTERVAL_SECONDS=300
APIFY_API_TOKEN=your_apify_token_here
APIFY_FACEBOOK_ACTOR_INPUT=

# مزود الذكاء الاصطناعي
AI_PROVIDER=ollama
AI_MODEL=qwen2.5:7b
```

ثم طبّق ترحيلات قاعدة البيانات (اختياري في وضع المصدر):

```bash
alembic upgrade head
python seed.py    # (اختياري) بيانات تجريبية + حساب المسؤول الافتراضي
```

---

## 3. إنشاء حزمة التثبيت (SignalDesk_Setup.exe)

### الخطوة 1 — تشغيل سكريبت البناء التلقائي

سِكريبت البناء يكتشف Inno Setup تلقائياً (PATH ← سجل Windows ← المسارات القياسية) ويبحث عن `ISCC.exe`:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\deployment\build_installer.ps1
```

### الخطوة 2 — تحديد مسار Inno Setup يدوياً (عند الحاجة)

إذا لم يكتشف السكربت المحرّك تلقائياً:

```powershell
.\deployment\build_installer.ps1 -InnoPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

### الخطوة 3 — الناتج ومكانه

بعد نجاح البناء:

```text
📦 releases\SignalDesk_Setup.exe   ← حجم تقريبي ~2.6 ميغابايت
```

> ℹ️ حجم الحزمة النهائي يُستثنى منه تلقائيًا: ملفات `.git`، مجلد `tests`، مجلدات `node_modules`، الوسيط `frontend/.next`، مصدّر NSSM (يبقى `nssm.exe` فقط)، مثبّت Inno Setup نفسه، وقواعد البيانات المحلية.

### بنية حزمة التثبيت (ما بداخلها)

```text
{app}/
├── main.py                      # نقطة انطلاق خادم FastAPI
├── config.py                    # الإعدادات المركزية
├── requirements.txt             # اعتمادات Python (يُثبَّتها install-service.ps1)
├── app/                         # نواة النظام (API، النماذج، الخدمات)
├── migrations/                  # ترحيلات Alembic
├── frontend/out/                # الواجهة المبنية (تُقدَّم مباشرة)
├── assets/                      # الأيقونات
├── deployment/                  # سكربتات التثبيت/الخدمة/البناء
├── tools/nssm/nssm-2.24/win64/nssm.exe   # مُشغّل خدمة Windows (NSSM)
└── seed.py, alembic.ini, ...
```

---

## 4. دليل المستخدم النهائي للتثبيت (End-User Installation Guide)

> هذا القسم موجّه للمستخدم النهائي الذي سيشغّل `SignalDesk_Setup.exe` على جهازه.

### الخطوة 1 — تشغيل المثبّت

انقر نقرًا مزدوجًا على:

```text
SignalDesk_Setup.exe
```

> 🔐 **مطلوب:** موافقة UAC برتبة **مسؤول (Administrator)** — لأن التثبيت يُسجّل خدمة Windows ويضيف قاعدة جدار حماية. إن لم تكن لديك صلاحيات، ستتوقف خطوات التثبيت التلقائية.

اتبع معالج Inno Setup:

| خطوة المعالج | الإجراء الافتراضي |
| :--- | :--- |
| الترخيص | راجع الشروط ثم **Next** |
| مجلد التثبيت | `{autopf}\SignalDesk` (افتراضي) |
| Tasks | اترك المهمة الأساسية **محددة** ثم **Next** |
| التثبيت | انتظر — ينفّذ تثبيت الخدمة تلقائيًا |

### الخطوة 2 — ماذا يفعل المثبّت تلقائيًا؟

عند اكتمال التثبيت، يقوم `deployment\install-service.ps1` بما يلي تلقائيًا:

1. **تهيئة بيئة Python:** ينشئ `.venv` داخل `{app}\` إذا لم تكن موجودة، ويشغّل `ensurepip` ثم `pip install -r requirements.txt`.
2. **بناء الواجهة:** ينفّذ `npm run build` داخل `{app}\frontend` (يتطلب Node.js على الجهاز، ويتخطّى بهدوء إن لم يكن متوفرًا لأن `frontend/out` محزومة مسبقًا).
3. **تنزيل NSSM:** يبحث عن `nssm.exe` داخل `tools\nssm\...\win64\`، وإن لم يجده ينزّله من [nssm.cc](https://nssm.cc/release/nssm-2.24.zip).
4. **تسجيل خدمة Windows باسم `SignalDeskServer`:**
   - الأمر: `python -m uvicorn main:app --host 0.0.0.0 --port 8000`
   - نوع البدء: **تلقائي** (`SERVICE_AUTO_START`) — تبدأ مع الجهاز دون تدخل.
   - إعادة التشغيل تلقائيًا عند التعطل (AppExit=Restart، تأخير 5 ثوانٍ).
   - سجلات منفصلة في `{app}\logs\service_stdout.log` و`service_stderr.log`.
5. **قاعدة جدار الحماية:** ينشئ قاعدة `SignalDesk Server Access` للسماح بالدخول على المنفذ `8000`.
6. **تشغيل الخدمة** والتحقق من صحة `/health`.
7. **إنشاء اختصارات مباشرة** تفتح الواجهة على [http://127.0.0.1:8000](http://127.0.0.1:8000):
   - اختصار `SignalDesk` على **سطح المكتب**.
   - اختصار `SignalDesk` في **قائمة ابدأ** (Program Group).

### الخطوة 3 — التحقق من نجاح التثبيت

افتح متصفحك على:

```text
http://127.0.0.1:8000
```

أو من جهاز آخر على الشبكة المحلية:

```text
http://<IP-of-this-machine>:8000
```

ثم سجّل الدخول بالحساب الافتراضي:

| الحقل | القيمة |
| :--- | :--- |
| **البريد الإلكتروني** | `admin@example.com` |
| **كلمة المرور** | `admin123` |

> ⚠️ **تنبيه أمني:** غيّر كلمة المرور فوراً بعد أول تسجيل دخول من صفحة الملف الشخصي.

---

## 5. التحكم بالخدمة (Service Control)

الخدمة تعمل تلقائياً في الخلفية. للتحكم اليدوي:

### عبر PowerShell (بصلاحية مسؤول)

```powershell
# حالة الخدمة
Get-Service SignalDeskServer

# إيقاف / تشغيل / إعادة تشغيل
Stop-Service SignalDeskServer
Start-Service SignalDeskServer
Restart-Service SignalDeskServer

# فحص صحة الخادم
Invoke-RestMethod http://127.0.0.1:8000/health
```

> ✅ الحالة الصحية = `Running`، والاستجابة = `healthy`.

### عبر واجهة الخدمات (services.msc)

1. اضغط `Win + R` واكتب `services.msc` ثم Enter.
2. في القائمة ابحث عن **`SignalDeskServer`**.
3. بزر الفأرة الأيمن: **Start / Stop / Restart**، أو **Properties** لتغيير نوع البدء إلى **Automatic**.

### تغيير المنفذ (اختياري)

المنفذ معرَّف في **مصدر واحد** (`SIGNALDESK_PORT`) لضمان تطابق الاستماع مع الفحص الذاتي:

```powershell
.\deployment\set-service-port.ps1 -Port 8000
# للاستماع على هذا الجهاز فقط بدل شبكة محلية:
.\deployment\set-service-port.ps1 -Port 8000 -HostAddress 127.0.0.1
```

> إذا عدّلت منفذ الخدمة، حدّث `SIGNALDESK_PORT` في `.env` ليطابق، وإلا سيظهر تحذير `differs from SELF_CHECK_PORT`.

---

## 6. إزالة التثبيت (Clean Uninstall)

### الطريقة الموصى بها — إزالة التطبيقات من Windows

1. `Settings → Apps → Installed apps` (أو `Apps & features`).
2. ابحث عن **`SignalDesk`**.
3. **Uninstall** ← سيُشغّل `deployment\uninstall-service.ps1` تلقائيًا.

### يدويًا — عبر PowerShell (بصلاحية مسؤول)

```powershell
.\deployment\uninstall-service.ps1
```

### ما الذي يُنظَّف تلقائيًا؟

| العنصر | النتيجة |
| :--- | :--- |
| **خدمة `SignalDeskServer`** | ✅ إيقاف + إزالة تسجيلها من Windows |
| **قاعدة جدار الحماية `SignalDesk Server Access`** | ✅ حذف |
| **اختصارات سطح المكتب / قائمة ابدأ** | ✅ حذف عبر Inno Setup |
| **مجلد التثبيت `{app}\` ومحتواه** | ✅ حذف (بما فيه `.venv`، السجلات، قاعدة البيانات المحلية إن وُجدت) |

> 🔒 **حذف احتياطي:** يزيل `Uninstall` كل شيء داخل `{app}\`. **انسخ أي بيانات أو قواعد بيانات تريد الاحتفاظ بها قبل إزالة التثبيت.**

---

## 7. استكشاف الأخطاء وحلولها (Troubleshooting)

| المشكلة | الحل |
| :--- | :--- |
| `Inno Setup not found` | مرّر المسار يدويًا: `.\deployment\build_installer.ps1 -InnoPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"` |
| فشل بناء الحزمة: `file in use` | مجلد `releases` مستثنى تلقائيًا؛ تأكد أن ملف `SignalDesk_Setup.exe` غير قيد التشغيل |
| الخدمة `SignalDeskServer` لا تبدأ | راجع `{app}\logs\service_stderr.log`؛ شغّل `Invoke-RestMethod http://127.0.0.1:8000/health` |
| المنفذ 8000 محجوب | غيّر المنفذ عبر `set-service-port.ps1`، أو أوقف العملية التي تستخدمه |
| لا يظهر اختصار سطح المكتب | أنشئه يدويًا: افتح `http://127.0.0.1:8000` ← اسحب العنوان إلى سطح المكتب |
| فشل `npm run build` عند التثبيت | يُتجاهل بأمان — `frontend/out` محزومة مسبقًا ويعمل النظام بدونها |

---

<div align="center">

📖 للعودة إلى [الREADME الرئيسي](README.md) • دليل المستخدم الكامل: [USER_GUIDE_AR.md](deployment/USER_GUIDE_AR.md)

</div>