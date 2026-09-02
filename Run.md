# تشغيل SignalDesk

## المتطلبات

- Python وبيئة المشروع الافتراضية `venv`
- Node.js وnpm

## 1. تشغيل Backend

افتح نافذة PowerShell من جذر المشروع ثم نفّذ:

```powershell
cd "C:\Users\Hosam\Documents\SignalDesk"
venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

عند ظهور الرسالة التالية، يكون الخادم جاهزًا:

```text
Uvicorn running on http://127.0.0.1:8000
```

توثيق API متاح على:

```text
http://127.0.0.1:8000/docs
```

يمكن التحكم في توثيق وإخراج الـ API من ملف `.env`:

```env
API_DOCS_ENABLED=true
API_OPENAPI_ENABLED=true
API_DOCS_URL=/docs
API_REDOC_URL=/redoc
API_OPENAPI_URL=/openapi.json
CORS_ALLOW_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
```

وتصدير ملف OpenAPI يتم عبر:

```powershell
venv\Scripts\python.exe export_openapi.py --output openapi.json
```

## 2. تشغيل Frontend

افتح نافذة PowerShell ثانية ثم نفّذ:

```powershell
cd "C:\Users\Hosam\Documents\SignalDesk\frontend"
& "C:\Program Files\nodejs\npm.cmd" run dev
```

استخدم `npm.cmd` بدل `npm` لأن سياسة تنفيذ PowerShell على هذا الجهاز تمنع تشغيل `npm.ps1`.

افتح التطبيق من:

```text
http://127.0.0.1:3000
```

## بيانات الدخول الافتراضية

```text
البريد الإلكتروني: admin@example.com
كلمة المرور: admin123
```

## إيقاف الخوادم

انتقل إلى نافذة الـ Backend أو Frontend واضغط:

```text
Ctrl+C
```

## إعداد المشروع على جهاز جديد

من جذر المشروع، أنشئ البيئة الافتراضية وثبّت حزم Python:

```powershell
cd "C:\Users\Hosam\Documents\SignalDesk"
py -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

ثبّت حزم الواجهة:

```powershell
cd "C:\Users\Hosam\Documents\SignalDesk\frontend"
& "C:\Program Files\nodejs\npm.cmd" install
```
