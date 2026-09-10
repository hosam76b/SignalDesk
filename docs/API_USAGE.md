# طريقة استخدام والتحكم في API

هذا الملف يشرح تشغيل واجهات SignalDesk API، الوصول إلى التوثيق التفاعلي، تصدير ملف OpenAPI، والتحكم في ظهور التوثيق من ملف البيئة `.env`.

## تشغيل خادم API

من جذر المشروع شغّل الخادم الخلفي باستخدام بيئة المشروع الافتراضية:

```powershell
cd "C:\Users\Hosam\Documents\SignalDesk"
venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

بعد التشغيل سيكون الخادم متاحاً على:

```text
http://127.0.0.1:8000
```

## روابط التوثيق

عند تفعيل التوثيق، يمكن استخدام الروابط التالية:

```text
Swagger UI:   http://127.0.0.1:8000/docs
ReDoc:        http://127.0.0.1:8000/redoc
OpenAPI JSON: http://127.0.0.1:8000/openapi.json
```

استخدم Swagger UI لتجربة المسارات مباشرة من المتصفح، خصوصاً المسارات التي تحتاج `Bearer Token` بعد تسجيل الدخول.

## تسجيل الدخول واستخدام التوكن

سجل الدخول عبر:

```http
POST /api/auth/login
```

مثال باستخدام PowerShell:

```powershell
$login = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/login" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"email":"admin@example.com","password":"admin123"}'

$token = $login.access_token
```

بعدها أرسل التوكن مع الطلبات المحمية:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/auth/me" `
  -Headers @{ Authorization = "Bearer $token" }
```

## تصدير OpenAPI إلى ملف

لتوليد ملف OpenAPI JSON للواجهة الأمامية أو لأدوات خارجية:

```powershell
venv\Scripts\python.exe export_openapi.py --output openapi.json
```

يمكن اختيار مسار مختلف:

```powershell
venv\Scripts\python.exe export_openapi.py --output frontend\openapi.json
```

ولإخراج JSON مضغوط بدون تنسيق:

```powershell
venv\Scripts\python.exe export_openapi.py --output openapi.json --compact
```

## التحكم من ملف `.env`

أضف أو عدّل القيم التالية في ملف `.env` داخل جذر المشروع:

```env
API_DOCS_ENABLED=true
API_OPENAPI_ENABLED=true
API_DOCS_URL=/docs
API_REDOC_URL=/redoc
API_OPENAPI_URL=/openapi.json
CORS_ALLOW_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
```

معنى الإعدادات:

| الإعداد | الوظيفة |
| --- | --- |
| `API_DOCS_ENABLED` | إظهار أو إخفاء Swagger UI و ReDoc. |
| `API_OPENAPI_ENABLED` | إتاحة أو إيقاف ملف OpenAPI من الخادم. عند جعله `false` تتوقف روابط `/docs` و `/redoc` أيضاً. |
| `API_DOCS_URL` | تغيير مسار Swagger UI. |
| `API_REDOC_URL` | تغيير مسار ReDoc. |
| `API_OPENAPI_URL` | تغيير مسار OpenAPI JSON. |
| `CORS_ALLOW_ORIGINS` | تحديد عناوين الواجهة الأمامية المسموح لها بالاتصال، مفصولة بفواصل. |

## أمثلة جاهزة

### بيئة تطوير محلية

```env
API_DOCS_ENABLED=true
API_OPENAPI_ENABLED=true
CORS_ALLOW_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
```

### إخفاء Swagger و ReDoc مع إبقاء OpenAPI

```env
API_DOCS_ENABLED=false
API_OPENAPI_ENABLED=true
```

في هذه الحالة يبقى الرابط التالي متاحاً:

```text
http://127.0.0.1:8000/openapi.json
```

### إيقاف كل توثيق API من الخادم

```env
API_DOCS_ENABLED=false
API_OPENAPI_ENABLED=false
```

في هذه الحالة لن تكون روابط Swagger أو ReDoc أو OpenAPI متاحة من الخادم.

## اختبار سريع

بعد تعديل `.env` أعد تشغيل خادم الباكند، ثم تحقق من الإعدادات:

```powershell
venv\Scripts\python.exe -c "from main import app; print(app.docs_url, app.redoc_url, app.openapi_url)"
```

وتحقق من توليد OpenAPI:

```powershell
venv\Scripts\python.exe export_openapi.py --output openapi.json
```

## التكامل عبر الويب هوك (n8n وغيره)

يتيح SignalDesk إرسال الأحداث إلى أنظمة الأتمتة الخارجية مثل n8n عبر ويب هوكات متعددة تُدار من قاعدة البيانات.
جميع مسارات الإدارة تتطلب صلاحية المسؤول الأعلى (`super_admin`)، ويمكن التحكم بها أيضاً من واجهة الإعدادات: «إعدادات مساحة العمل» ← «إعدادات الويب هوك».

### مسارات إدارة الويب هوك

| المسار | الوظيفة |
| --- | --- |
| `GET /api/webhooks/events` | قائمة الأحداث المدعومة. |
| `GET /api/webhooks` | عرض كل الاشتراكات مع حالة آخر إرسال. |
| `POST /api/webhooks` | إنشاء اشتراك جديد (`name`, `url`, `secret`, `events`, `is_active`). |
| `GET /api/webhooks/{id}` | تفاصيل اشتراك واحد. |
| `PATCH /api/webhooks/{id}` | تعديل اشتراك (السر يبقى كما هو ما لم يُرسل). |
| `DELETE /api/webhooks/{id}` | حذف اشتراك مع سجل إرسالاته. |
| `POST /api/webhooks/{id}/test` | إرسال حدث تجريبي موقّع للتحقق من الاتصال. |
| `GET /api/webhooks/{id}/deliveries` | سجل محاولات الإرسال (الحالة، رمز HTTP، الخطأ، المدة). |
| `POST /api/webhooks/post-ingested` | إرسال دفعة منشورات يدوياً (أي مستخدم مسجّل). |

### الأحداث المدعومة

| الحدث | متى يُرسَل |
| --- | --- |
| `post_ingested` | عند استيعاب منشورات جديدة من المصادر. |
| `alert_triggered` | عند رصد تنبيه جديد عالي/حرج لموضوع. |
| `report_ready` | عند توليد تقرير PDF تنفيذي. |
| `analysis_completed` | عند انتهاء دفعة تحليل الذكاء الاصطناعي. |

### شكل الحمولة والتوقيع

كل إرسال هو `POST` بصيغة JSON بالشكل:

```json
{
  "event": "post_ingested",
  "sent_at": "2026-09-03T12:00:00+00:00",
  "data": { "..." : "..." }
}
```

الترويسات المرسَلة:

```text
X-Webhook-Event: post_ingested
X-Webhook-Delivery: <معرّف فريد لكل محاولة>
X-Webhook-Signature: sha256=<HMAC-SHA256 للجسم الخام بالسر المشترك>
```

عند ضبط `secret` للاشتراك، تحقق في n8n من التوقيع بمقارنة `X-Webhook-Signature` مع HMAC-SHA256 المحسوب على جسم الطلب الخام.

### مثال: إنشاء ويب هوك لـ n8n

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/webhooks" `
  -Method Post -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"name":"n8n workflow","url":"https://n8n.example.com/webhook/abc","secret":"shared-secret","events":["post_ingested","alert_triggered"]}'
```

> ملاحظة توافقية: المتغير `POST_INGESTED_WEBHOOK_URL` في `.env` ما زال يعمل كقناة إرسال إضافية لحدث `post_ingested`، لكن الإدارة من قاعدة البيانات هي الطريقة الموصى بها.