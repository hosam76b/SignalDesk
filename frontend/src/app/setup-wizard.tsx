"use client";

import { Check, ChevronLeft, ChevronRight, Database, Eye, EyeOff, LoaderCircle, ShieldCheck } from "lucide-react";
import { useState } from "react";

type Lang = "ar" | "en";
type DatabaseType = "sqlite" | "postgresql";
type Role = "super_admin" | "topic_manager" | "analyst" | "observer" | "topic_admin" | "topic_monitor";

type WizardProps = {
  lang: Lang;
  toggleLanguage: () => void;
  onInitialized: (token: string, role: Role) => void;
};

const text = {
  ar: {
    title: "إعداد SignalDesk", subtitle: "جهّز بيئة المراقبة الآمنة في أربع خطوات.", database: "قاعدة البيانات", admin: "المشرف العام", system: "المنظومة والذكاء الاصطناعي", review: "المراجعة والتشغيل",
    sqlite: "SQLite محلية", postgres: "PostgreSQL خادم", test: "اختبار الاتصال", tested: "تم اختبار الاتصال", next: "التالي", back: "السابق", deploy: "تهيئة وتشغيل المنظومة", fullName: "الاسم الكامل", identity: "البريد الإلكتروني أو اسم المستخدم", password: "كلمة المرور", confirm: "تأكيد كلمة المرور", platform: "اسم المنظومة أو الجهة", provider: "مزود الذكاء الاصطناعي", apiKey: "مفتاح API (اختياري الآن)", interval: "فاصل المراقبة بالدقائق", path: "مسار ملف قاعدة البيانات", host: "المضيف", port: "المنفذ", name: "اسم القاعدة", username: "المستخدم", dbPassword: "كلمة مرور القاعدة", passwordMismatch: "كلمتا المرور غير متطابقتين.", passwordWeak: "استخدم 8 محارف على الأقل تتضمن حروفاً وأرقاماً.", testFirst: "اختبر الاتصال قبل المتابعة.", ready: "جاهز للتهيئة", configured: "الإعدادات التي ستطبق", error: "تعذر إكمال التهيئة.", language: "English",
  },
  en: {
    title: "Set up SignalDesk", subtitle: "Prepare the secure monitoring workspace in four steps.", database: "Database", admin: "Super admin", system: "System & AI", review: "Review & deploy",
    sqlite: "Local SQLite", postgres: "PostgreSQL server", test: "Test connection", tested: "Connection verified", next: "Next", back: "Back", deploy: "Initialize and launch", fullName: "Full name", identity: "Email or username", password: "Password", confirm: "Confirm password", platform: "Platform or organization name", provider: "AI provider", apiKey: "API key (optional for now)", interval: "Monitoring interval (minutes)", path: "Database file path", host: "Host", port: "Port", name: "Database name", username: "Username", dbPassword: "Database password", passwordMismatch: "Passwords do not match.", passwordWeak: "Use at least 8 characters including letters and numbers.", testFirst: "Test the connection before continuing.", ready: "Ready to initialize", configured: "Configuration to apply", error: "Unable to complete setup.", language: "العربية",
  },
};

export function SetupWizard({ lang, toggleLanguage, onInitialized }: WizardProps) {
  const copy = text[lang];
  const [step, setStep] = useState(0);
  const [databaseType, setDatabaseType] = useState<DatabaseType>("sqlite");
  const [database, setDatabase] = useState({ path: "media_monitor.db", host: "localhost", port: 5432, name: "media_monitor", username: "", password: "" });
  const [admin, setAdmin] = useState({ fullName: "", identity: "", password: "", confirm: "" });
  const [system, setSystem] = useState({ appName: "SignalDesk", provider: "ollama", apiKey: "", interval: 5 });
  const [tested, setTested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const passwordStrong = admin.password.length >= 8 && /[A-Za-z]/.test(admin.password) && /\d/.test(admin.password);
  const databasePayload = { type: databaseType, ...database };

  const testConnection = async () => {
    setBusy(true); setError(""); setTested(false);
    try {
      const response = await fetch("/api/setup/test-db", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(databasePayload) });
      const result = await response.json();
      if (!result.success) throw new Error(result.message);
      setTested(true);
    } catch (cause) { setError(cause instanceof Error ? cause.message : copy.error); }
    finally { setBusy(false); }
  };
  const next = () => {
    setError("");
    if (step === 0 && !tested) return setError(copy.testFirst);
    if (step === 1 && admin.password !== admin.confirm) return setError(copy.passwordMismatch);
    if (step === 1 && !passwordStrong) return setError(copy.passwordWeak);
    setStep((current) => Math.min(3, current + 1));
  };
  const deploy = async () => {
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/setup/initialize", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ full_name: admin.fullName, email_or_username: admin.identity, password: admin.password, confirm_password: admin.confirm, database: databasePayload, app_name: system.appName, ai_provider: system.provider, ai_api_key: system.apiKey, monitoring_interval_minutes: Number(system.interval) }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? copy.error);
      onInitialized(result.access_token, result.role);
    } catch (cause) { setError(cause instanceof Error ? cause.message : copy.error); }
    finally { setBusy(false); }
  };
  const setDb = (key: string, value: string | number) => { setDatabase((current) => ({ ...current, [key]: value })); setTested(false); };
  const stepNames = [copy.database, copy.admin, copy.system, copy.review];
  return <main className="setup-screen" dir={lang === "ar" ? "rtl" : "ltr"}>
    <section className="setup-identity"><span className="brand-mark large"><span /></span><p className="eyebrow">SignalDesk / First run</p><h1>{copy.title}</h1><p>{copy.subtitle}</p></section>
    <section className="setup-panel"><button type="button" className="language-button" onClick={toggleLanguage}>{copy.language}</button><ol className="setup-steps">{stepNames.map((name, index) => <li key={name} className={index <= step ? "active" : ""}><span>{index < step ? <Check size={13} /> : index + 1}</span>{name}</li>)}</ol>
      <div className="setup-form"><h2>{stepNames[step]}</h2>
        {step === 0 && <><div className="setup-choice"><button type="button" className={databaseType === "sqlite" ? "selected" : ""} onClick={() => { setDatabaseType("sqlite"); setTested(false); }}><Database size={19} /><strong>{copy.sqlite}</strong><small>media_monitor.db</small></button><button type="button" className={databaseType === "postgresql" ? "selected" : ""} onClick={() => { setDatabaseType("postgresql"); setTested(false); }}><Database size={19} /><strong>{copy.postgres}</strong><small>External server</small></button></div>{databaseType === "sqlite" ? <label>{copy.path}<input value={database.path} onChange={(event) => setDb("path", event.target.value)} /></label> : <div className="setup-grid"><label>{copy.host}<input value={database.host} onChange={(event) => setDb("host", event.target.value)} /></label><label>{copy.port}<input type="number" value={database.port} onChange={(event) => setDb("port", Number(event.target.value))} /></label><label>{copy.name}<input value={database.name} onChange={(event) => setDb("name", event.target.value)} /></label><label>{copy.username}<input value={database.username} onChange={(event) => setDb("username", event.target.value)} /></label><label className="full">{copy.dbPassword}<input type="password" value={database.password} onChange={(event) => setDb("password", event.target.value)} /></label></div>}<button type="button" className="secondary-button" onClick={testConnection} disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <Database size={16} />}{copy.test}</button>{tested && <p className="setup-success"><Check size={16} />{copy.tested}</p>}</>}
        {step === 1 && <><label>{copy.fullName}<input value={admin.fullName} onChange={(event) => setAdmin({ ...admin, fullName: event.target.value })} required /></label><label>{copy.identity}<input value={admin.identity} onChange={(event) => setAdmin({ ...admin, identity: event.target.value })} required /></label><label>{copy.password}<span className="password-input"><input type={showPassword ? "text" : "password"} value={admin.password} onChange={(event) => setAdmin({ ...admin, password: event.target.value })} /><button type="button" onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</button></span></label><div className={`strength ${passwordStrong ? "good" : ""}`}><i /><i /><i /><span>{passwordStrong ? "Strong" : copy.passwordWeak}</span></div><label>{copy.confirm}<input type="password" value={admin.confirm} onChange={(event) => setAdmin({ ...admin, confirm: event.target.value })} /></label></>}
        {step === 2 && <><label>{copy.platform}<input value={system.appName} onChange={(event) => setSystem({ ...system, appName: event.target.value })} /></label><label>{copy.provider}<select value={system.provider} onChange={(event) => setSystem({ ...system, provider: event.target.value })}><option value="ollama">Ollama (local)</option><option value="google_ai_studio">Google AI Studio</option><option value="openrouter">OpenRouter</option><option value="custom_openai">OpenAI-compatible</option></select></label><label>{copy.apiKey}<input type="password" value={system.apiKey} onChange={(event) => setSystem({ ...system, apiKey: event.target.value })} /></label><label>{copy.interval}<input type="number" min="1" max="1440" value={system.interval} onChange={(event) => setSystem({ ...system, interval: Number(event.target.value) })} /></label></>}
        {step === 3 && <div className="setup-review"><ShieldCheck size={30} /><strong>{copy.ready}</strong><p>{copy.configured}</p><dl><dt>{copy.database}</dt><dd>{databaseType === "sqlite" ? database.path : `${database.host}:${database.port}/${database.name}`}</dd><dt>{copy.admin}</dt><dd>{admin.fullName} ({admin.identity})</dd><dt>{copy.system}</dt><dd>{system.appName} / {system.provider} / {system.interval} min</dd></dl></div>}
        {error && <p className="form-error">{error}</p>}<footer className="setup-actions">{step > 0 && <button type="button" className="secondary-button" onClick={() => setStep(step - 1)}><ChevronRight size={16} />{copy.back}</button>}{step < 3 ? <button type="button" className="primary-button" onClick={next}>{copy.next}<ChevronLeft size={16} /></button> : <button type="button" className="primary-button" onClick={deploy} disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}{copy.deploy}</button>}</footer>
      </div>
    </section>
  </main>;
}