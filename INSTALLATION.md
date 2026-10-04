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
6. [تطبيق شريط المهام (System Tray App)](#6-تطبيق-شريط-المهام-system-tray-app)
7. [إزالة التثبيت (Clean Uninstall)](#7-إزالة-التثبيت-clean-uninstall)
8. [استكشاف الأخطاء وحلولها (Troubleshooting)](#8-استكشاف-الأخطاء-وحلولها-troubleshooting)

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
| **Python** | `3.11` أو `3.12` فقط | تشغيل الخادم (FastAPI) | ⚠️ **لا تستخدم 3.13** — السبب في [تنبيه Python 3.13](#تنبيه-لا-تستخدم-python-313) |
| **Node.js** | `18.x` أو `20.x` | بناء واجهة المستخدم | مطلوب **للمطوّر فقط** — الحزمة النهائية تحتوي `frontend/out` جاهزاً |
| **Inno Setup** | `6.7.3` | بناء حزمة التثبيت | [https://jrsoftware.org/isinfo.php](https://jrsoftware.org/isinfo.php) |
| **PostgreSQL** | `14` أو أحدث | قاعدة البيانات | مطلوب على جهاز التثبيت النهائي (يُنشئه `install-service.ps1`) |
| **Git** | أحدث إصدار | استنساخ المستودع | مستودع عام، لا يحتاج حساب |

### تنبيه: لا تستخدم Python 3.13

يقوم `install-service.ps1` بإنشاء البيئة الافتراضية بـ **3.12 ثم 3.11 ثم 3.10** بهذا الترتيب، ويتجاهل 3.13 عمداً.

السبب: حزمة **`numpy`** — وهي تبعية غير مباشرة عبر `opencv-python` و`easyocr` — **لا تنشر عجلات (wheels) جاهزة لـ Python 3.13**. وعندما لا يجد pip عجلة جاهزة، يلجأ إلى **البناء من المصدر**، وهذا يتطلب مترجم C/C++ (`cl` أو `clang`) غير مثبّت افتراضياً. النتيجة:

```text
error: metadata-generation-failed
  × Encountered error while generating package metadata.
  ╰─> numpy
```

والمشكلة الأخطر أن **pip يُلغي تثبيت كل الحزم دفعة واحدة**، فتبقى `.venv` شبه فارغة (تحتوي `pip` فقط)، وتفشل الخدمة عند التشغيل:

```text
C:\Program Files (x86)\SignalDesk\.venv\Scripts\python.exe: No module named uvicorn
```

وتعيد NSSM تشغيلها كل 5 ثوانٍ حتى تتعلّق حالة الخدمة في **`Paused`**، فيظهر عند المستخدم:

```text
ERR_CONNECTION_REFUSED
```

لذلك أضاف `install-service.ps1` بعد التثبيت **فحصاً صارماً** يُفشل التثبيت برسالة واضحة بدلاً من إنتاج خدمة معطوبة:

```powershell
& $python -c "import uvicorn, fastapi"
```

> ✅ **للتحقق من بيئة قائمة:** شغّل `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` ثم `.\.venv\Scripts\python.exe -c "import uvicorn, fastapi"`.
> 🌐 **الاتصال بالإنترنت مطلوب** لتنزيل العجلات من PyPI.

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
# إنشاء البيئة الافتراضية (بإصدار 3.11 أو 3.12)
py -3.12 -m venv .venv

# تفعيلها (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# تثبيت الاعتماديات
python -m pip install --upgrade pip
pip install -r requirements.txt

# (اختياري) متطلبات التطوير والاختبارات
pip install -r requirements-dev.txt

# التحقق من نجاح التثبيت
python -c "import uvicorn, fastapi; print('OK')"
```

> ⚠️ **استخدم `py -3.12` أو `py -3.11` صراحةً.** الأمر `py -3` قد يختار Python 3.13 وهو غير مدعوم بسبب numpy — راجع [تنبيه Python 3.13](#تنبيه-لا-تستخدم-python-313).
> ✅ للتأكد: `python --version` يجب أن يعرض `3.11.x` أو `3.12.x`.

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
📦 releases\SignalDesk_Setup.exe   ← الحجم النهائي: ~2.61 ميغابايت
```

> ℹ️ للتحقق من الحجم الفعلي بعد أي بناء:
> ```powershell
> Get-Item .\releases\SignalDesk_Setup.exe | ForEach-Object { "{0:N2} MB" -f ($_.Length / 1MB) }
> ```
>
> 📉 الهبوط من ~20.9 ميغابايت إلى ~2.61 ميغابايت ناتج عن ضبط قائمة `Excludes` في قسم `[Files]`:
>
> | ما تم استثناؤه | المساحة الموفّرة (قبل الضغط) |
> | :--- | :--- |
> | `innosetup-*.exe` (مثبّت Inno Setup نفسه كان في جذر المشروع) | ~10.1 MB |
> | `frontend\.next` (وسيط البناء) | ~36.1 MB |
> | `node_modules` | ~445 MB |
> | `.git` | ~10.6 MB |
> | `tests` و`test_*.py` | ~0.3 MB |
> | `*.db` و`*.db-shm` و`*.db-wal` (قواعد SQLite المحلية) | متغيّر |
> | `tools\nssm\nssm-2.24\src` (يبقى `nssm.exe` فقط) | ~0.4 MB |
>
> ✅ **لا تكرار في الاختصارات:** اختصارات سطح المكتب وقائمة ابدأ يملكها Inno Setup وحده عبر قسم `[Icons]`. وأُزيل إنشاء الاختصارات من `install-service.ps1` لأن الاثنين معاً كانا ينشئان نسختين على سطح المكتب (`.lnk` و`.url`).

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

## 6. تطبيق شريط المهام (System Tray App)

أداة `SignalDesk Monitor` هي **إضافة اختيارية** تعيش في منطقة الإشعارات بجانب الساعة، وتوفّر وصولاً سريعاً إلى حالة الخدمة. وهي **ليست** جزءاً من الخدمة نفسها.

### سلوك زر Exit

> ⚠️ **مهم:** عند النقر على **Exit** من قائمة شريط المهام، يتم إغلاق **واجهة التحكم المصغرة فقط**، **دون** إيقاف خدمة `SignalDeskServer` الخلفية.
>
> الخادم يظل يعمل، ويظل النظام متاحاً على `http://127.0.0.1:8000`، ولا تتأثر أي عملية جارية (سحب، تحليل ذكاء اصطناعي، تقارير).
>
> لإيقاف الخدمة فعلياً، استخدم `Stop-Service SignalDeskServer` أو واجهة `services.msc` أو عنصر **Stop service** من نفس قائمة الأيقونة.

### إعادة تشغيل الأيقونة يدوياً

إذا أغلقت الأداة (أو لم تظهر بعد التثبيت) شغّلها من **PowerShell** أو **CMD**:

```powershell
wscript "C:\Program Files (x86)\SignalDesk\deployment\start_tray.vbs"
```

أو من موجه الأوامر:

```cmd
wscript "C:\Program Files (x86)\SignalDesk\deployment\start_tray.vbs"
```

> ℹ️ لا تظهر نافذة سوداء، لأن الأداة تعمل عبر `pythonw.exe`.
> 🔍 السكربت يبحث عن Python بالترتيب: `.venv\Scripts\pythonw.exe` ← `venv\Scripts\pythonw.exe` ← **البحث في `PATH`**. إن لم يجد Python، يعرض رسالة توضيحية بدل الفشل الصامت.

### التشغيل التلقائي مع بدء تشغيل ويندوز

الأيقونة مسجَّلة تلقائياً في مجلد بدء التشغيل بواسطة `install-service.ps1`. ولإعادة إنشاء الاختصار يدوياً:

1. افتح مجلد بدء التشغيل: اضغط **`Win + R`** واكتب:
   ```text
   shell:startup
   ```
2. أنشئ اختصاراً لملف `start_tray.vbs` داخل المجلد الذي فُتح:
   ```text
   C:\Program Files (x86)\SignalDesk\deployment\start_tray.vbs
   ```
3. اضبط خصائص الاختصار كما في الجدول أدناه لضمان عمله بشكل صحيح:

**الإعداد الصحيح للاختصار:**

| الحقل | القيمة |
| :--- | :--- |
| **Target** (الهدف) | `%SystemRoot%\System32\wscript.exe` |
| **Arguments** (المعطيات) | `"C:\Program Files (x86)\SignalDesk\deployment\start_tray.vbs"` |
| **Start in** | `C:\Program Files (x86)\SignalDesk` |
| **Icon** | `C:\Program Files (x86)\SignalDesk\assets\signaldesk-monitor.ico` |

> أو الأسهل: شغّل سكربت التثبيت مرة أخرى بصلاحية مسؤول، فهو يُسجّل الاختصار في Startup تلقائياً.

### استكشاف مشاكل شريط المهام

| المشكلة | الحل |
| :--- | :--- |
| الأيقونة لا تظهر بعد تشغيل السكربت | افتح سهم **إظهار الأيقونات المخفية** بجانب ساعة النظام |
| رسالة "SignalDesk Monitor needs Python" | ثبّت Python 3.11/3.12 على جهازك، أو شغّل `install-service.ps1` لإصلاح البيئة |
| لا تعمل القائمة (الخدمة تعمل لكن لا استجابة) | شغّل PowerShell **بصلاحية مسؤول** — إجراءات الخدمة تتطلب صلاحية |
| تظهر أيقونتان | أغلق الزائدة من قائمة **Exit** ثم شغّل نسخة واحدة فقط |

---

## 7. إزالة التثبيت (Clean Uninstall)

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

## 8. استكشاف الأخطاء وحلولها (Troubleshooting)

| المشكلة | الحل |
| :--- | :--- |
| `Inno Setup not found` | مرّر المسار يدويًا: `.\deployment\build_installer.ps1 -InnoPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"` |
| فشل بناء الحزمة: `file in use` | مجلد `releases` مستثنى تلقائيًا؛ تأكد أن ملف `SignalDesk_Setup.exe` غير قيد التشغيل |
| الخدمة `SignalDeskServer` لا تبدأ | راجع `{app}\logs\service_stderr.log`؛ شغّل `Invoke-RestMethod http://127.0.0.1:8000/health` |
| المنفذ 8000 محجوب | غيّر المنفذ عبر `set-service-port.ps1`، أو أوقف العملية التي تستخدمه |
| لا يظهر اختصار سطح المكتب | أنشئه يدويًا: افتح `http://127.0.0.1:8000` ← اسحب العنوان إلى سطح المكتب |
| فشل `npm run build` عند التثبيت | يُتجاهل بأمان — `frontend/out` محزومة مسبقًا ويعمل النظام بدونها |
| **الخدمة `Paused` + `ERR_CONNECTION_REFUSED`** | راجع `{app}\logs\service_stderr.log`. غالباً `No module named uvicorn` لأن `pip install` فشل — احذف `{app}\.venv` وأعد تشغيل `install-service.ps1` |
| `error: metadata-generation-failed` / `numpy` | النظام يستخدم Python 3.13. احذف `{app}\.venv` وأعد التثبيت ليُنشئه السكربت بـ 3.11/3.12، أو ثبّت [Build Tools for Visual Studio](https://visualstudio.microsoft.com/downloads/) |
| الخدمة تنهار كل 5 ثوانٍ | انظر صف `Paused` أعلاه — السبب دائماً بيئة Python ناقصة الحزم |
| اختصاران على سطح المكتب | أحدهما متبقٍ من إصدار قديم. احذف `SignalDesk.lnk` واترك `SignalDesk.url` فقط |
| `APIFY_FACEBOOK_ACTOR_INPUT` غير موجود في `.env.example` | المتغير معرّف في `config.py`؛ أضفه يدوياً إلى `.env` عند الحاجة |
| رسالة "SignalDesk Monitor needs Python" | ثبّت Python 3.11/3.12 على جهاز المستخدم، أو شغّل `install-service.ps1` |
| أيقونة شريط المهام لا تظهر | افتح سهم **إظهار الأيقونات المخفية**، أو شغّل `wscript "{app}\deployment\start_tray.vbs"` |

---

<div align="center">

📖 للعودة إلى [الREADME الرئيسي](README.md) • دليل المستخدم الكامل: [USER_GUIDE_AR.md](deployment/USER_GUIDE_AR.md)

</div>
