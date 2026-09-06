# دليل تشغيل SignalDesk

## قبل البدء

نفذ الأوامر من مجلد المشروع `SignalDesk`. تحتاج إلى Python وNode.js مرة واحدة فقط لتثبيت النظام.

للتشغيل الدائم كخدمة، استخدم Python `3.10` أو `3.11` أو `3.12` وNode.js `20 LTS`. ثبّت Git فقط عندما تريد تنزيل النظام من GitHub أو إنشاء حزمة نقل.

## تشغيل سريع للتجربة

افتح PowerShell داخل مجلد المشروع، ثم نفذ:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm.cmd --prefix .\frontend run build
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

أبق نافذة PowerShell مفتوحة، ثم افتح هذا العنوان في المتصفح على جهاز السيرفر:

```text
http://127.0.0.1:8000
```

لإيقاف التشغيل التجريبي، ارجع إلى نافذة PowerShell واضغط `Ctrl+C`.

## التشغيل الأول فقط

إذا لم يكن للنظام مشرف سابق، ستظهر شاشة الإعداد تلقائياً:

1. اختر `SQLite محلية` واترك المسار `media_monitor.db` كما هو، ثم اختر `اختبار الاتصال`.
2. أدخل اسم المشرف والبريد أو اسم المستخدم وكلمة مرور تحتوي 8 محارف على الأقل وحروفاً وأرقاماً.
3. اختر مزود الذكاء الاصطناعي. يمكن ترك مفتاح API فارغاً وإضافته لاحقاً.
4. اختر `تهيئة وتشغيل المنظومة`. سيتم تسجيل دخول المشرف تلقائياً.

لا تظهر شاشة الإعداد إذا كانت القاعدة تحتوي على مشرف سابق. هذا صحيح لحماية النظام من إنشاء مشرف ثانٍ دون تصريح.

## التثبيت كخدمة ويندوز دائمة

استخدم هذه الطريقة لجهاز السيرفر الذي يجب أن يبقى يعمل بعد تسجيل الخروج أو إعادة تشغيل Windows.

1. افتح **PowerShell بصلاحية مسؤول**: ابحث عن PowerShell، ثم اختر `Run as administrator`.
2. انتقل إلى مجلد المشروع:

```powershell
Set-Location "C:\Users\Hosam\Documents\SignalDesk"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

3. شغّل المثبت:

```powershell
.\deployment\install-service.ps1
```

المثبت يجهز `pip` ويثبت المتطلبات تلقائياً، ثم ينشئ خدمة Windows باسم `SignalDeskServer`، ويبني الواجهة، ويفتح المنفذ `8000` في جدار الحماية، ويضيف اختصارين على سطح المكتب.

إذا لم توجد `.venv` أو `venv` على جهاز جديد، ينشئ المثبت بيئة `.venv` تلقائياً.

## تنزيل النظام من GitHub إلى جهاز سيرفر جديد

نفذ الخطوات التالية مرة واحدة على جهاز السيرفر. افتح PowerShell بصلاحية مسؤول:

```powershell
Set-Location "C:\"
git clone https://github.com/hosam76b/SignalDesk.git SignalDesk
Set-Location "C:\SignalDesk"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\deployment\install-service.ps1
```

بعد ظهور رسالة نجاح، افتح `http://127.0.0.1:8000`. في أول تشغيل تظهر شاشة الإعداد لإنشاء المشرف وإعداد قاعدة بيانات جديدة.

لتحديث نسخة مثبتة من GitHub مستقبلاً، أوقف الخدمة ثم نفذ:

```powershell
Set-Location "C:\SignalDesk"
Stop-Service SignalDeskServer
git pull origin main
.\deployment\install-service.ps1
```

## إنشاء حزمة للنقل دون GitHub

هذه الحزمة تحتوي على المصدر البرمجي فقط، ولا تتضمن الأسرار أو قاعدة البيانات. قبل إنشائها احفظ تعديلاتك وارفعها إلى GitHub أو نفذ commit محلياً، ثم شغّل:

```powershell
Set-Location "C:\Users\Hosam\Documents\SignalDesk"
.\deployment\package-release.ps1
```

ستجد ملف ZIP في مجلد `releases`. انقله إلى جهاز السيرفر، فك ضغطه مثلاً في `C:\SignalDesk`، ثم نفذ خطوات `التثبيت كخدمة ويندوز دائمة` من داخل ذلك المجلد.

## نقل البيانات إلى جهاز جديد

قاعدة البيانات لا تدخل GitHub ولا حزمة المصدر. انقلها يدوياً فقط عندما تريد الاحتفاظ بالمستخدمين والمواضيع والمنشورات:

1. أوقف الخدمة على الجهاز القديم: `Stop-Service SignalDeskServer`.
2. انسخ الملفات التالية إلى مكان آمن: `.env` و`media_monitor.db` ومجلد `media_uploads` إن كانت الوسائط مطلوبة.
3. ثبّت SignalDesk على الجهاز الجديد أولاً، ثم أوقف خدمته.
4. ضع الملفات المنسوخة في جذر المشروع الجديد واستبدل الملفات الموجودة عند الطلب.
5. شغّل الخدمة: `Start-Service SignalDeskServer`.

لا ترفع `.env` أو `media_monitor.db` أو مجلد `media_uploads` إلى GitHub، لأنها قد تتضمن مفاتيح وصول وبيانات تشغيلية.

## فتح النظام بعد التثبيت

على جهاز السيرفر، افتح اختصار `SignalDesk` على سطح المكتب أو استخدم:

```text
http://127.0.0.1:8000
```

من جهاز آخر متصل بالشبكة نفسها، استخدم:

```text
http://عنوان-IP-للسيرفر:8000
```

لمعرفة عنوان السيرفر، نفذ على جهاز السيرفر:

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" } | Select-Object -ExpandProperty IPAddress
```

مثال: `http://192.168.1.50:8000`.

## التحقق من حالة الخدمة

نفذ في PowerShell:

```powershell
Get-Service SignalDeskServer
Invoke-RestMethod http://127.0.0.1:8000/health
```

يجب أن تكون حالة الخدمة `Running`، وأن يرجع الفحص `healthy`.

## السجلات وحل التوقف

بعد أي تعديل في الكود أو ملف `.env`، لا تشغل نسخة يدوية منفصلة على المنفذ 8000. أعد تحميل خدمة Windows نفسها من PowerShell بصلاحية Administrator:

```powershell
Set-Location "C:\Users\Hosam\Documents\SignalDesk"
.\deployment\restart-service.ps1
```

استخدم اختصار `SignalDesk Monitor` أو افتح الملفات التالية:

```text
logs\service_stdout.log
logs\service_stderr.log
```

لإعادة تشغيل الخدمة:

```powershell
Restart-Service SignalDeskServer
```

## إزالة الخدمة

افتح PowerShell بصلاحية مسؤول من مجلد المشروع، ثم نفذ:

```powershell
.\deployment\uninstall-service.ps1
```

يزيل هذا الأمر خدمة Windows وقاعدة جدار الحماية. لا يحذف قاعدة البيانات أو المنشورات.