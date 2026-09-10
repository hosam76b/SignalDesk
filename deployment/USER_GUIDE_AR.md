# دليل التنصيب والتشغيل الكامل على Windows

هذا الدليل موجه لمستخدم جديد يريد تشغيل SignalDesk على جهازه الشخصي. اتبع الخطوات بالترتيب. المسار الموصى به لجهاز شخصي هو SQLite مع خدمة Windows.

## التثبيت التلقائي باستخدام المعالج

بعد الحصول على ملفات المعالج، افتح PowerShell بصلاحية Administrator من أي مجلد وشغّل المعالج باستخدام مساره. لا تحتاج إلى تنفيذ `Set-Location` إلى مسار ثابت:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& "D:\Downloads\SignalDesk\deployment\setup-wizard.ps1"
```

ستظهر نافذة لاختيار مكان المشروع. اختر مجلداً يحتوي نسخة SignalDesk، أو اختر مجلداً فارغاً ليقوم المعالج بتنزيل المستودع داخله. يمكنك أيضاً تمرير المكان مباشرة دون نافذة:

```powershell
& "D:\Downloads\SignalDesk\deployment\setup-wizard.ps1" -ProjectRoot "D:\Apps\SignalDesk"
```

إذا اخترت مجلداً فارغاً، يحتاج المعالج إلى Git واتصال بالإنترنت، ثم ينفذ التنزيل قبل بقية الخطوات.

ينفذ المعالج تلقائياً الخطوات التالية بالترتيب:

1. يفحص وجود Python وNode.js وnpm.
2. ينشئ `.env` ويضبط SQLite ومفتاح أمان عشوائياً في التثبيت الجديد.
3. ينشئ `.venv` ويثبت حزم Python ومتصفح Playwright.
4. يثبت حزم الواجهة ويبني `frontend\out`.
5. يثبت خدمة Windows باسم `SignalDeskServer` ويفتح المنفذ `8000`.
6. يفحص `/health` ثم يفتح المتصفح.

بعد ذلك أكمل شاشة `إعداد SignalDesk` التي تظهر في المتصفح: اختبر SQLite، أنشئ حساب المشرف، اختر مزود الذكاء الاصطناعي، ثم اضغط `تهيئة وتشغيل المنظومة`. لا يحذف المعالج ملف `.env` الموجود ولا يستبدل إعداداتك الحالية إلا بقيمة SQLite الأساسية.

## 1. تثبيت البرامج المطلوبة

ثبّت البرامج التالية:

1. Python `3.10` أو `3.11` أو `3.12`، مع تفعيل `Add Python to PATH` أثناء التثبيت.
2. Node.js `20 LTS`، ويتضمن `npm`.
3. Git for Windows لتنزيل المشروع من GitHub.

اختبر التثبيت من PowerShell:

```powershell
python --version
node --version
npm --version
git --version
```

يجب أن تظهر أرقام إصدارات للأدوات الأربعة.

## 2. تنزيل المشروع

```powershell
Set-Location "C:\"
git clone https://github.com/hosam76b/SignalDesk.git SignalDesk
Set-Location "C:\SignalDesk"
```

سيظهر مجلد `C:\SignalDesk`، ويحتوي على مجلدات مثل `app` و`frontend` و`deployment` و`migrations` و`tests`.

## 3. إنشاء ملف الإعداد

```powershell
Copy-Item .env.example .env
notepad .env
```

ضع في الملف على الأقل:

```env
DB_URL=sqlite:///./media_monitor.db
SECRET_KEY=ضع-هنا-مفتاحا-عشوائيا-طويلا
AI_PROVIDER=ollama
SCRAPING_ENABLED=true
```

يمكن ترك مفاتيح Telegram وReddit وYouTube وApify فارغة في البداية. لإنشاء مفتاح عشوائي:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

انسخ الناتج إلى `SECRET_KEY`.

## 4. تجهيز Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
```

إذا رفض PowerShell تشغيل البيئة الافتراضية:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

يجب أن يظهر `(.venv)` في بداية سطر PowerShell.

## 5. تجهيز الواجهة

```powershell
Set-Location .\frontend
npm install
Set-Location ..
npm.cmd --prefix .\frontend run build
```

بعد نجاح البناء سيظهر غالباً مجلد `frontend\out`.

## 6. تثبيت SignalDesk كخدمة Windows

افتح PowerShell بصلاحية Administrator، ثم نفذ:

```powershell
Set-Location "C:\SignalDesk"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\deployment\install-service.ps1
```

ينشئ المثبت خدمة `SignalDeskServer`، ويبني الواجهة، ويفتح المنفذ `8000` في جدار الحماية، وينشئ اختصاري `SignalDesk` و`SignalDesk Monitor` على سطح المكتب. كما ينشئ `.venv` تلقائياً إذا لم تكن موجودة.

## 7. فتح النظام لأول مرة

افتح `http://127.0.0.1:8000` أو اضغط اختصار `SignalDesk`.

ستظهر شاشة `إعداد SignalDesk` من أربع خطوات:

1. اختر `SQLite محلية`، واترك المسار `media_monitor.db`، ثم اضغط `اختبار الاتصال`.
2. أدخل الاسم والبريد أو اسم المستخدم وكلمة مرور من 8 محارف على الأقل تحتوي حروفاً وأرقاماً.
3. اختر مزود الذكاء الاصطناعي. يمكن ترك مفتاح API فارغاً وإضافته لاحقاً.
4. راجع الإعدادات واضغط `تهيئة وتشغيل المنظومة`.

سيتم إنشاء الجداول وحساب المشرف وموضوع `General Monitoring`، ثم تسجيل الدخول تلقائياً. سيظهر ملف `media_monitor.db` في جذر المشروع.

لا تظهر شاشة الإعداد مرة أخرى إذا كانت القاعدة تحتوي على مشرف.

## 8. تسجيل الدخول بعد ذلك

افتح `http://127.0.0.1:8000` واستخدم بيانات المشرف التي أنشأتها. لا تحتاج إلى تشغيل `npm run dev` في التشغيل الدائم؛ فالواجهة المبنية يقدمها Backend على المنفذ `8000`.

## 9. التحقق من الخدمة

```powershell
Get-Service SignalDeskServer
Invoke-RestMethod http://127.0.0.1:8000/health
```

يجب أن تكون الحالة `Running` وأن يعيد الفحص `healthy`.

## 10. ما سيظهر على الجهاز

بعد التثبيت ستجد داخل `C:\SignalDesk`:

```text
.venv\              بيئة Python
.env                إعدادات النظام والمفاتيح
media_monitor.db    قاعدة SQLite
frontend\out\       نسخة الواجهة المبنية
media_uploads\      الوسائط المرفوعة
logs\               سجلات الخدمة
tools\nssm\         أداة تشغيل الخدمة
```

وعلى سطح المكتب:

```text
SignalDesk.lnk
SignalDesk Monitor.lnk
```

وفي خدمات Windows ستجد `SignalDeskServer`، وتبدأ تلقائياً بعد إعادة تشغيل الجهاز.

## 11. أيقونة المراقبة

تظهر أيقونة SignalDesk في منطقة الإشعارات بجانب الساعة. إذا لم تظهر:

```powershell
wscript.exe .\deployment\start_tray.vbs
```

منها يمكن فتح النظام أو بدء الخدمة أو إيقافها أو إعادة تشغيلها أو فتح مجلد `logs`.

## 12. الوصول من جهاز آخر

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" } | Select-Object -ExpandProperty IPAddress
```

إذا كان العنوان `192.168.1.50` افتح من جهاز آخر على الشبكة نفسها:

```text
http://192.168.1.50:8000
```

## 13. إعداد Ollama محلياً

ثبّت Ollama ثم نفذ:

```powershell
ollama pull qwen2.5:7b
ollama list
```

يستخدم SignalDesk افتراضياً `http://localhost:11434`. عند استخدام Ollama المحلي تبقى بيانات التحليل على الجهاز.

## 14. إعداد مزود سحابي

لـ Google AI Studio:

```env
AI_PROVIDER=google_ai_studio
GOOGLE_AI_STUDIO_API_KEY=ضع-مفتاح-Gemini-هنا
```

أو لـ OpenRouter:

```env
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=ضع-المفتاح-هنا
```

بعد تعديل `.env` أعد تشغيل الخدمة من PowerShell بصلاحيات Administrator:

```powershell
.\deployment\restart-service.ps1
```

## 15. السجلات وحل المشكلات

السجلات موجودة في:

```text
C:\SignalDesk\logs\service_stdout.log
C:\SignalDesk\logs\service_stderr.log
```

بعد تعديل الكود أو `.env` استخدم:

```powershell
.\deployment\restart-service.ps1
```

لا تشغل نسخة Uvicorn يدوية على المنفذ `8000` أثناء تشغيل الخدمة.

## 16. الروابط المفيدة

```text
الواجهة:       http://127.0.0.1:8000
فحص الصحة:     http://127.0.0.1:8000/health
توثيق API:     http://127.0.0.1:8000/docs
توثيق ReDoc:   http://127.0.0.1:8000/redoc
```

## إزالة الخدمة

```powershell
.\deployment\uninstall-service.ps1
```

يزيل الأمر خدمة Windows وقاعدة الجدار الناري، لكنه لا يحذف قاعدة البيانات أو المنشورات.
