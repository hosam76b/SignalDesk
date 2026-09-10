/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Check,
  Database,
  ExternalLink,
  Edit3,
  Eye,
  EyeOff,
  FileText,
  Globe2,
  LayoutDashboard,
  LayoutGrid,
  List,
  LogOut,
  Menu,
  PanelLeftClose,
  Plus,
  Radio,
  Search,
  Settings2,
  Share2,
  ShieldCheck,
  Sparkles,
  Star,
  Trash2,
  UserCog,
  Users,
  X,
} from "lucide-react";
import { UserManagement } from "./admin-users";
import { TopicAdminHub as TopicManagement } from "./topic-admin-hub";
import { AuditDashboard } from "./audit-dashboard";
import { PropagationGraphView } from "./propagation-graph-view";
import { SetupWizard } from "./setup-wizard";

const API = process.env.NEXT_PUBLIC_API_URL ?? (
  typeof window !== "undefined" && window.location.port !== "8000"
    ? "http://127.0.0.1:8000"
    : ""
);
type Lang = "ar" | "en";
type Page =
  | "overview"
  | "feed"
  | "spider"
  | "graph"
  | "management"
  | "topics"
  | "members"
  | "users"
  | "automation"
  | "knowledge"
  | "audit"
  | "prompts"
  | "approvals"
  | "proposals"
  | "profile";
type Post = {
  id: number;
  topic_id: number;
  platform: string;
  title: string | null;
  content: string;
  author: string;
  scraped_at: string;
  severity_level: string | null;
  is_flagged: boolean;
  is_important: boolean;
  is_dangerous: boolean;
  post_url?: string | null;
  media_urls?: unknown[];
};
type AuditRecord = {
  id: number;
  user_id: number | null;
  post_id: number | null;
  action: string;
  details: Record<string, boolean> | null;
  created_at: string;
};
type Stats = {
  total_posts: number;
  posts_by_platform: Record<string, number>;
  posts_by_severity: Record<string, number>;
  flagged_posts: number;
};
type Role = "super_admin" | "topic_manager" | "analyst" | "observer" | "topic_admin" | "topic_monitor";
type Topic = { id: number; title: string; description?: string | null };
type AiStatus = { enabled: boolean; mode: string; provider: string; model?: string | null; available_models?: string[] };
type UpdateStatus = {
  update_available: boolean;
  current_version: string;
  latest_version: string | null;
  release_url: string | null;
  error?: string | null;
};
type PromptTemplate = { id: number; topic_id: number; name: string; template: string; variables?: string | null; provider?: string; model_name?: string; is_active: boolean; created_by_id?: number | null };
type AlertItem = {
  id: string;
  type: string;
  severity: string;
  status: "unread" | "acknowledged" | "resolved";
  title: string;
  description: string;
  topic_id: number;
  created_at: string;
  metadata?: Record<string, unknown>;
};
type AlertSummary = { total_alerts: number; unread: number; acknowledged: number; resolved: number; by_type?: Record<string, number> };
type Item = {
  id: number;
  topic_id?: number;
  name?: string;
  platform?: string;
  url_or_handle?: string;
  word_or_phrase?: string;
  category?: string;
  target_type?: string;
  apify_actor_id?: string | null;
  status?: string;
  is_active: boolean;
  approval_status?: "pending" | "approved" | "rejected";
  proposed_by_id?: number | null;
  reviewed_by_id?: number | null;
  reviewed_at?: string | null;
};
type ApprovalsSummary = { sources: Item[]; keywords: Item[] };
type ScraperStatus = { status: "idle" | "running"; message: string; last_run?: string | null; is_running: boolean };
type ScrapingResult = { success: boolean; total_sources: number; total_posts_found: number; new_posts_saved: number; errors: { source?: string; error?: string }[]; duration_seconds: number; sources_processed: Record<string, { sources?: number; posts_found?: number; posts_saved?: number }> };
type SpiderRunStatus = {
  run_id: string;
  status: "queued" | "running" | "completed";
  topic_id: number;
  pages_crawled: number;
  accepted: number;
  discarded: number;
  active_keywords: string[];
  search_topics?: string[];
  target_keywords?: string[];
  seed_urls?: string[];
  relevance_threshold?: number;
  max_depth?: number;
  proxy_enabled?: boolean;
  errors: { url?: string; error?: string }[];
  started_at: string;
  finished_at: string | null;
};
type SpiderActiveStatus = { is_running: boolean; active_runs: number; total_runs: number; last_run_id: string | null; last_status: string | null };

const AI_PROVIDER_DEFAULTS: Record<string, { model: string; baseUrl: string; models: string[] }> = {
  ollama: { model: "qwen2.5:7b", baseUrl: "http://localhost:11434", models: ["qwen2.5:7b", "llama3.1:8b", "mistral:7b"] },
  openrouter: { model: "openai/gpt-4o-mini", baseUrl: "https://openrouter.ai/api/v1", models: ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "google/gemini-2.0-flash-001"] },
  google_ai_studio: { model: "gemini-2.0-flash", baseUrl: "https://generativelanguage.googleapis.com/v1beta/models", models: ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"] },
  custom_openai: { model: "gpt-4o-mini", baseUrl: "https://api.openai.com/v1", models: ["gpt-4o-mini", "gpt-4.1-mini", "local-model"] },
};

function SpiderIcon({ size = 18, color = "currentColor", className }: { size?: number; color?: string; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <circle cx="12" cy="9.5" r="2.6" />
      <path d="M12 12.1v6.9" />
      <path d="M9.6 9 3.5 5.2" />
      <path d="M9.2 10.3 2.2 11.4" />
      <path d="M9.6 12.4 3.9 17.2" />
      <path d="M14.4 9l6.1-3.8" />
      <path d="M14.8 10.3l7-1.1" />
      <path d="M14.4 12.4l5.7 4.8" />
      <path d="M10.2 6.8 8.6 3.2" />
      <path d="M13.8 6.8l1.6-3.6" />
    </svg>
  );
}
const labels = {
  ar: {
    overview: "نظرة عامة",
    feed: "موجز الاستخبارات",
    spider: "متابعة السبايدر",
    graph: "شبكة الانتشار و CIB",
    management: "الروابط والكلمات المفتاحية",
    automation: "مراقبة الأتمتة",
    knowledge: "قاعدة المعرفة",
    audit: "سجلات التدقيق",
    add: "إضافة جديدة",
    sources: "الروابط والمصادر",
    keywords: "الكلمات المفتاحية",
    prompts: "إعدادات الذكاء الاصطناعي",
    approvals: "طلبات الموافقة",
    proposals: "تقديم مقترح",
    profile: "الملف الشخصي والأمان",
    signout: "تسجيل الخروج",
  },
  en: {
    overview: "Overview",
    feed: "Intelligence feed",
    spider: "Spider monitor",
    graph: "Propagation & CIB",
    management: "Sources & keywords",
    automation: "Automation monitor",
    knowledge: "Knowledge base",
    audit: "Audit logs",
    add: "Add new",
    sources: "Sources",
    keywords: "Keywords",
    prompts: "AI settings",
    approvals: "Pending approvals",
    proposals: "Submit proposal",
    profile: "Profile & security",
    signout: "Sign out",
  },
};
// Tracks the active UI language so ApiError messages (thrown from a shared, lang-agnostic
// request() helper) still localize correctly; kept in sync by Home's language toggle.
let currentApiLang: Lang = "ar";
function setApiLang(next: Lang) {
  currentApiLang = next;
}
function getApiErrorDetail(body: unknown): string | undefined {
  if (!body || typeof body !== "object" || !("detail" in body)) return undefined;
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return undefined;
  const firstError = detail[0];
  if (!firstError || typeof firstError !== "object" || !("msg" in firstError) || typeof firstError.msg !== "string") return undefined;
  const location = "loc" in firstError && Array.isArray(firstError.loc) ? firstError.loc.at(-1) : undefined;
  return location ? `${String(location)}: ${firstError.msg}` : firstError.msg;
}
class ApiError extends Error {
  status: number;
  constructor(status: number, detail?: string) {
    const messages =
      currentApiLang === "ar"
        ? {
            401: "انتهت جلسة الدخول.",
            403: "لا تملك صلاحية لهذا الإجراء.",
            422: "تحقق من البيانات المدخلة.",
            default: "تعذر إكمال الطلب.",
          }
        : {
            401: "Your session has expired.",
            403: "You don't have permission for this action.",
            422: "Check the submitted data.",
            default: "Unable to complete the request.",
          };
    super(detail || (
      status === 401
        ? messages[401]
        : status === 403
          ? messages[403]
          : status === 422
            ? messages[422]
            : messages.default
    ));
    this.status = status;
  }
}
async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (response.status === 401) {
    window.localStorage.removeItem("signaldesk_token");
    window.localStorage.removeItem("signaldesk_role");
    window.dispatchEvent(new Event("signaldesk-auth-expired"));
  }
  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, getApiErrorDetail(body));
  }
  return response.json();
}
async function get<T>(path: string, token: string): Promise<T> {
  return request<T>(path, token);
}
function Login({
  lang,
  onLogin,
  toggle,
}: {
  lang: Lang;
  onLogin: (token: string, role: Role) => void;
  toggle: () => void;
}) {
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("admin123");
  const [totpCode, setTotpCode] = useState("");
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(false);
  const [mode, setMode] = useState<"login" | "forgot" | "reset">("login");
  const [resetToken, setResetToken] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("reset_token");
    if (token) {
      setResetToken(token);
      setMode("reset");
    }
  }, []);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const response = await fetch(`${API}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, totp_code: totpCode || undefined }),
      });
      if (!response.ok) throw new ApiError(response.status);
      const data = (await response.json()) as {
        access_token: string;
        role: Role;
      };
      onLogin(data.access_token, data.role);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر تسجيل الدخول" : "Unable to sign in"));
    }
  };
  const submitForgot = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      const response = await fetch(`${API}/api/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!response.ok) throw new ApiError(response.status);
      setNotice(
        lang === "ar"
          ? "إذا كان البريد الإلكتروني مسجلاً لدينا، فسيصلك رابط إعادة تعيين كلمة المرور."
          : "If that email is registered, a password reset link has been sent.",
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر إرسال الطلب." : "Unable to send the request."));
    }
  };
  const submitReset = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      const response = await fetch(`${API}/api/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: resetToken, new_password: resetPassword }),
      });
      if (!response.ok) throw new ApiError(response.status);
      setNotice(lang === "ar" ? "تم تحديث كلمة المرور. يمكنك تسجيل الدخول الآن." : "Password updated. You can sign in now.");
      setMode("login");
      window.history.replaceState({}, "", window.location.pathname);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر إعادة تعيين كلمة المرور." : "Unable to reset the password."));
    }
  };
  return (
    <main className="login-screen">
      <section className="login-art" dir={lang === "ar" ? "rtl" : "ltr"}>
        <span className="brand-mark large">
          <span />
        </span>
        <p className="eyebrow">Signaldesk</p>
        <h1>
          {lang === "ar" ? (
            <>
              راقب الإشارة.
              <br />
              افهم الصورة.
            </>
          ) : (
            <>
              See the signal.
              <br />
              Understand the picture.
            </>
          )}
        </h1>
        <p>
          {lang === "ar"
            ? "اجمع المصادر وتابع المخاطر من مساحة واحدة."
            : "Bring sources together and track risk from one place."}
        </p>
      </section>
      {mode === "login" ? (
        <form className="login-card" onSubmit={submit}>
          <button type="button" className="language-button" onClick={toggle}>
            {lang === "ar" ? "English" : "العربية"}
          </button>
          <p className="eyebrow">
            {lang === "ar" ? "الوصول الآمن" : "Secure access"}
          </p>
          <h2>{lang === "ar" ? "مرحباً بعودتك" : "Welcome back"}</h2>
          <p className="login-hint">
            {lang === "ar"
              ? "أدخل بياناتك للوصول إلى مساحة المراقبة"
              : "Enter your credentials to access the workspace"}
          </p>
          <label>
            {lang === "ar" ? "البريد الإلكتروني" : "Email"}
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              required
            />
          </label>
          <label>
            {lang === "ar" ? "كلمة المرور" : "Password"}
            <span className="password-input">
              <input
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                type={visible ? "text" : "password"}
                required
              />
              <button type="button" onClick={() => setVisible(!visible)}>
                {visible ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </span>
          </label>
          <label>
            {lang === "ar" ? "رمز التحقق (2FA - اختياري)" : "2FA code (optional)"}
            <input
              value={totpCode}
              onChange={(event) => setTotpCode(event.target.value)}
              inputMode="numeric"
              maxLength={6}
              placeholder="000000"
            />
          </label>
          {error && <p className="form-error">{error}</p>}
          {notice && <p className="connection-message">{notice}</p>}
          <button className="primary-button login-button" type="submit">
            {lang === "ar" ? "تسجيل الدخول" : "Sign in"}{" "}
            <ArrowUpRight size={16} />
          </button>
          <button type="button" className="text-button" onClick={() => { setError(""); setNotice(""); setMode("forgot"); }}>
            {lang === "ar" ? "نسيت كلمة المرور؟" : "Forgot password?"}
          </button>
        </form>
      ) : mode === "forgot" ? (
        <form className="login-card" onSubmit={submitForgot}>
          <button type="button" className="language-button" onClick={toggle}>
            {lang === "ar" ? "English" : "العربية"}
          </button>
          <p className="eyebrow">{lang === "ar" ? "استعادة كلمة المرور" : "Password recovery"}</p>
          <h2>{lang === "ar" ? "نسيت كلمة المرور" : "Forgot password"}</h2>
          <p className="login-hint">
            {lang === "ar"
              ? "أدخل بريدك الإلكتروني وسنرسل رابط إعادة تعيين صالح لمدة 15 دقيقة."
              : "Enter your email and we'll send a reset link valid for 15 minutes."}
          </p>
          <label>
            {lang === "ar" ? "البريد الإلكتروني" : "Email"}
            <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required />
          </label>
          {error && <p className="form-error">{error}</p>}
          {notice && <p className="connection-message">{notice}</p>}
          <button className="primary-button login-button" type="submit">
            {lang === "ar" ? "إرسال رابط الاستعادة" : "Send reset link"} <ArrowUpRight size={16} />
          </button>
          <button type="button" className="text-button" onClick={() => { setError(""); setNotice(""); setMode("login"); }}>
            {lang === "ar" ? "العودة لتسجيل الدخول" : "Back to sign in"}
          </button>
        </form>
      ) : (
        <form className="login-card" onSubmit={submitReset}>
          <button type="button" className="language-button" onClick={toggle}>
            {lang === "ar" ? "English" : "العربية"}
          </button>
          <p className="eyebrow">{lang === "ar" ? "تعيين كلمة مرور جديدة" : "Set a new password"}</p>
          <h2>{lang === "ar" ? "إعادة تعيين كلمة المرور" : "Reset password"}</h2>
          <label>
            {lang === "ar" ? "رمز إعادة التعيين" : "Reset token"}
            <input value={resetToken} onChange={(event) => setResetToken(event.target.value)} required />
          </label>
          <label>
            {lang === "ar" ? "كلمة المرور الجديدة" : "New password"}
            <input value={resetPassword} onChange={(event) => setResetPassword(event.target.value)} type="password" minLength={8} required />
          </label>
          {error && <p className="form-error">{error}</p>}
          {notice && <p className="connection-message">{notice}</p>}
          <button className="primary-button login-button" type="submit">
            {lang === "ar" ? "تحديث كلمة المرور" : "Update password"} <ArrowUpRight size={16} />
          </button>
          <button type="button" className="text-button" onClick={() => { setError(""); setNotice(""); setMode("login"); }}>
            {lang === "ar" ? "العودة لتسجيل الدخول" : "Back to sign in"}
          </button>
        </form>
      )}
    </main>
  );
}

function KnowledgeBase({ token, lang }: { token: string; lang: Lang }) {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicId, setTopicId] = useState<number | null>(null);
  const [documents, setDocuments] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const load = async (selected = topicId, query = search) => { if (!selected) return; try { setDocuments(await get<any[]>(`/api/knowledge/topics/${selected}/documents${query ? `?search=${encodeURIComponent(query)}` : ""}`, token)); } catch { setDocuments([]); } };
  useEffect(() => { get<Topic[]>("/api/v1/topics", token).then((items) => { setTopics(items); if (items[0]) setTopicId(items[0].id); }).catch(() => setTopics([])); }, [token]);
  useEffect(() => { void load(); }, [topicId]);
  useEffect(() => { const timer = window.setTimeout(() => void load(topicId, search), 300); return () => window.clearTimeout(timer); }, [search]);
  const upload = async () => { if (!topicId || !file || !title.trim()) { setMessage(lang === "ar" ? "أدخل العنوان واختر ملفًا." : "Enter a title and choose a file."); return; } setBusy(true); setMessage(""); try { const form = new FormData(); form.append("title", title); form.append("tags", tags); form.append("file", file); const response = await request<any>(`/api/knowledge/topics/${topicId}/documents`, token, { method: "POST", body: form }); setDocuments((current) => [response, ...current]); setTitle(""); setTags(""); setFile(null); setMessage(lang === "ar" ? "تمت إضافة الوثيقة." : "Document added."); } catch { setMessage(lang === "ar" ? "تعذر رفع الوثيقة." : "Unable to upload document."); } finally { setBusy(false); } };
  const remove = async (id: number) => { try { await request<void>(`/api/knowledge/documents/${id}`, token, { method: "DELETE" }); setDocuments((items) => items.filter((item) => item.id !== id)); } catch { setMessage(lang === "ar" ? "تعذر حذف الوثيقة." : "Unable to delete document."); } };
  return <div className="page-content knowledge-page"><div className="page-header"><div><p className="eyebrow">KNOWLEDGE BASE</p><h1>{lang === "ar" ? "قاعدة المعرفة" : "Knowledge base"}</h1><p className="subhead">{lang === "ar" ? "اجمع الوثائق المرجعية واربطها بمواضيع المراقبة." : "Collect reference documents and link them to monitoring topics."}</p></div></div>{message && <div className="connection-message">{message}</div>}<div className="knowledge-layout"><section className="panel knowledge-upload"><div className="panel-heading"><div><p className="eyebrow">ADD DOCUMENT</p><h2>{lang === "ar" ? "إضافة وثيقة مرجعية" : "Add reference document"}</h2></div><FileText size={20} color="var(--cyan)" /></div><label>{lang === "ar" ? "الموضوع" : "Topic"}<select value={topicId ?? ""} onChange={(event) => setTopicId(Number(event.target.value))}>{topics.map((topic) => <option value={topic.id} key={topic.id}>{topic.title}</option>)}</select></label><label>{lang === "ar" ? "عنوان الوثيقة" : "Document title"}<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder={lang === "ar" ? "مثال: تقرير المخاطر" : "Example: Risk report"} /></label><label>{lang === "ar" ? "الوسوم" : "Tags"}<input value={tags} onChange={(event) => setTags(event.target.value)} placeholder={lang === "ar" ? "سياسة، مخاطر، مرجع" : "policy, risk, reference"} /></label><label className="knowledge-file-field">{lang === "ar" ? "الملف" : "File"}<input type="file" accept=".txt,.md,.csv,.json,.pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /><small>{lang === "ar" ? "TXT، Markdown، CSV، JSON أو PDF حتى 20MB" : "TXT, Markdown, CSV, JSON up to 20MB"}</small></label><button type="button" className="primary-button knowledge-upload-button" disabled={busy} onClick={() => void upload()}>{busy ? <span className="loading-spinner" /> : <Plus size={15} />}{busy ? (lang === "ar" ? "جار الرفع..." : "Uploading...") : (lang === "ar" ? "إضافة إلى القاعدة" : "Add to knowledge base")}</button></section><section className="panel knowledge-library"><div className="panel-heading"><div><p className="eyebrow">LIBRARY</p><h2>{lang === "ar" ? "الوثائق المحفوظة" : "Saved documents"}</h2></div><span className="template-count">{documents.length}</span></div><div className="knowledge-toolbar"><select value={topicId ?? ""} onChange={(event) => setTopicId(Number(event.target.value))}>{topics.map((topic) => <option value={topic.id} key={topic.id}>{topic.title}</option>)}</select><label className="search-field"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={lang === "ar" ? "ابحث في الوثائق..." : "Search documents..."} /></label></div>{documents.length ? <div className="knowledge-documents">{documents.map((document) => <article className="knowledge-document" key={document.id}><div className="knowledge-file-icon"><FileText size={18} /></div><div><strong>{document.title}</strong><small>{document.filename} · {document.tags || (lang === "ar" ? "بدون وسوم" : "No tags")}</small>{document.extracted_text && <p>{document.extracted_text.slice(0, 180)}{document.extracted_text.length > 180 ? "..." : ""}</p>}</div><button className="icon-button danger-button" title={lang === "ar" ? "حذف الوثيقة" : "Delete document"} onClick={() => void remove(document.id)}><Trash2 size={15} /></button></article>)}</div> : <div className="empty-state"><FileText size={25} /><p>{lang === "ar" ? "لا توجد وثائق بعد." : "No documents yet."}</p></div>}</section></div></div>;
}

function AutomationMonitor({ token, role, lang }: { token: string; role: Role; lang: Lang }) {
  const [status, setStatus] = useState<ScraperStatus | null>(null);
  const [lastResult, setLastResult] = useState<ScrapingResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const canTrigger = role === "super_admin" || role === "topic_manager";

  const load = async () => {
    try {
      const [nextStatus, nextResult] = await Promise.all([
        get<ScraperStatus>("/api/scraper/status", token),
        get<ScrapingResult>("/api/scraper/last-result", token).catch(() => null),
      ]);
      setStatus(nextStatus);
      setLastResult(nextResult);
      setError("");
    } catch {
      setError(lang === "ar" ? "تعذر تحميل حالة الأتمتة." : "Unable to load automation status.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(timer);
  }, [token, lang]);

  const trigger = async () => {
    if (!canTrigger || running) return;
    setRunning(true);
    setError("");
    try {
      const result = await request<ScrapingResult>("/api/scraper/trigger", token, { method: "POST" });
      setLastResult(result);
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 409 ? (lang === "ar" ? "توجد دورة جمع تعمل حاليًا." : "A scraping cycle is already running.") : (lang === "ar" ? "تعذر تشغيل دورة الجمع." : "Unable to start scraping cycle."));
    } finally {
      setRunning(false);
    }
  };

  const dateLabel = (value?: string | null) => value ? new Intl.DateTimeFormat(lang === "ar" ? "ar" : "en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : (lang === "ar" ? "لم يبدأ بعد" : "Not run yet");
  const sourceRows = lastResult ? Object.entries(lastResult.sources_processed) : [];
  return (
    <div className="page-content automation-page">
      <div className="page-header">
        <div><p className="eyebrow">AUTOMATION CONTROL</p><h1>{lang === "ar" ? "مراقبة الأتمتة" : "Automation monitor"}</h1><p className="subhead">{lang === "ar" ? "تابع دورات جمع البيانات ومخرجاتها في الوقت الفعلي." : "Track data collection cycles and their live output."}</p></div>
        {canTrigger && <button className="primary-button" onClick={() => void trigger()} disabled={running || status?.is_running}>{running || status?.is_running ? <span className="loading-spinner" /> : <Radio size={15} />}{running || status?.is_running ? (lang === "ar" ? "جاري التشغيل" : "Running") : (lang === "ar" ? "تشغيل دورة الآن" : "Run cycle now")}</button>}
      </div>
      {error && <div className="data-error">{error}</div>}
      <div className="automation-status-banner">
        <span className={`automation-status-dot ${status?.is_running ? "running" : "idle"}`} />
        <div><strong>{status?.is_running ? (lang === "ar" ? "الأتمتة تعمل الآن" : "Automation is running") : (lang === "ar" ? "الأتمتة جاهزة" : "Automation is ready")}</strong><small>{status?.message ?? (loading ? (lang === "ar" ? "جار التحميل..." : "Loading...") : "")}</small></div>
        <span className="automation-refresh">{lang === "ar" ? "تحديث تلقائي كل 10 ثوانٍ" : "Auto-refresh every 10 seconds"}</span>
      </div>
      <div className="automation-summary">
        <div><Activity size={15} color="var(--cyan)" /><strong>{lastResult?.total_sources ?? "-"}</strong><small>{lang === "ar" ? "مصادر في آخر دورة" : "Sources in last cycle"}</small></div>
        <div><Database size={15} color="var(--cyan)" /><strong>{lastResult?.total_posts_found ?? "-"}</strong><small>{lang === "ar" ? "منشورات تم العثور عليها" : "Posts found"}</small></div>
        <div><Check size={15} color="#35b78d" /><strong>{lastResult?.new_posts_saved ?? "-"}</strong><small>{lang === "ar" ? "منشورات جديدة محفوظة" : "New posts saved"}</small></div>
        <div><AlertTriangle size={15} color="var(--coral)" /><strong>{lastResult?.errors.length ?? "-"}</strong><small>{lang === "ar" ? "أخطاء في آخر دورة" : "Errors in last cycle"}</small></div>
      </div>
      <div className="automation-grid">
        <div className="panel automation-panel"><div className="panel-heading"><div><p className="eyebrow">LAST RUN</p><h2>{lang === "ar" ? "آخر دورة جمع" : "Last collection cycle"}</h2></div><span className="badge badge-neutral">{dateLabel(status?.last_run)}</span></div>{lastResult ? <div className="automation-details"><div><span>{lang === "ar" ? "المدة" : "Duration"}</span><strong>{lastResult.duration_seconds.toFixed(1)}s</strong></div><div><span>{lang === "ar" ? "الحالة" : "Status"}</span><strong>{lastResult.success ? (lang === "ar" ? "نجحت" : "Success") : (lang === "ar" ? "جزئية" : "Partial")}</strong></div></div> : <div className="empty-state">{lang === "ar" ? "لا توجد دورة مكتملة بعد." : "No completed cycle yet."}</div>}</div>
        <div className="panel automation-panel"><div className="panel-heading"><div><p className="eyebrow">SOURCE OUTPUT</p><h2>{lang === "ar" ? "مخرجات المصادر" : "Source output"}</h2></div></div>{sourceRows.length ? <div className="automation-source-list">{sourceRows.map(([source, values]) => <div className="automation-source-row" key={source}><strong>{source.toUpperCase()}</strong><span>{values.posts_found ?? 0} {lang === "ar" ? "موجود" : "found"}</span><span className="badge badge-success">+{values.posts_saved ?? 0}</span></div>)}</div> : <div className="empty-state">{lang === "ar" ? "ستظهر النتائج بعد أول دورة." : "Results will appear after the first cycle."}</div>}</div>
      </div>
      {lastResult?.errors.length ? <div className="panel automation-panel"><div className="panel-heading"><div><p className="eyebrow">ATTENTION</p><h2>{lang === "ar" ? "الأخطاء التي تحتاج مراجعة" : "Errors requiring attention"}</h2></div></div><div className="automation-errors">{lastResult.errors.map((item, index) => <div key={`${item.source}-${index}`}><AlertTriangle size={14} /><span>{item.source ?? (lang === "ar" ? "مصدر غير معروف" : "Unknown source")}</span><small>{item.error ?? "Unknown error"}</small></div>)}</div></div> : null}
    </div>
  );
}

function SpiderMonitor({ token, lang }: { token: string; lang: Lang }) {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicId, setTopicId] = useState<number | null>(null);
  const [searchTopics, setSearchTopics] = useState("");
  const [targetKeywords, setTargetKeywords] = useState("");
  const [seedUrls, setSeedUrls] = useState("");
  const [relevanceThreshold, setRelevanceThreshold] = useState(30);
  const [maxDepth, setMaxDepth] = useState(1);
  const [proxyEnabled, setProxyEnabled] = useState(false);
  const [runs, setRuns] = useState<SpiderRunStatus[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [injectText, setInjectText] = useState("");
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    get<Topic[]>("/api/v1/topics", token)
      .then((items) => { setTopics(items); setTopicId((current) => current ?? items[0]?.id ?? null); })
      .catch(() => setTopics([]));
  }, [token]);

  const loadRuns = () => get<SpiderRunStatus[]>("/api/v1/spider/runs", token).then(setRuns).catch(() => setRuns([]));
  useEffect(() => {
    void loadRuns();
    const timer = window.setInterval(() => void loadRuns(), 5000);
    return () => window.clearInterval(timer);
  }, [token]);

  const activeRun = runs.find((run) => run.run_id === activeRunId) ?? runs.find((run) => run.status === "running") ?? runs[0] ?? null;

  const getRunTargetKeywords = (run: SpiderRunStatus) => {
    if (run.target_keywords) return run.target_keywords;
    if (run.search_topics || run.seed_urls) return [];
    return run.active_keywords;
  };

  const getRunParameterCount = (run: SpiderRunStatus) => {
    if (run.search_topics || run.target_keywords || run.seed_urls) {
      return (run.seed_urls?.length ?? 0) + (run.search_topics?.length ?? 0) + (run.target_keywords?.length ?? 0);
    }
    return run.active_keywords.length;
  };

  const applyRunParameters = (run: SpiderRunStatus) => {
    setTopicId(run.topic_id);
    setSearchTopics((run.search_topics ?? []).join(", "));
    setTargetKeywords(getRunTargetKeywords(run).join(", "));
    setSeedUrls((run.seed_urls ?? []).join("\n"));
    setRelevanceThreshold(run.relevance_threshold ?? 30);
    setMaxDepth(run.max_depth ?? 1);
    setProxyEnabled(run.proxy_enabled ?? false);
    setActiveRunId(run.run_id);
  };

  const rerun = async (run: SpiderRunStatus) => {
    if (starting) return;
    setStarting(true);
    setError("");
    setMessage("");
    try {
      const result = await request<{ run_id: string; status: string; message: string }>("/api/v1/spider/run", token, {
        method: "POST",
        body: JSON.stringify({
          topic_id: run.topic_id,
          search_topics: run.search_topics ?? [],
            target_keywords: getRunTargetKeywords(run),
          seed_urls: run.seed_urls ?? [],
          relevance_threshold: run.relevance_threshold ?? 30,
          max_depth: run.max_depth ?? 1,
          proxy_enabled: run.proxy_enabled ?? false,
        }),
      });
      setActiveRunId(result.run_id);
      setMessage(result.message || (lang === "ar" ? "تمت إعادة تشغيل السبايدر." : "Spider rerun started."));
      await loadRuns();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر إعادة تشغيل الزحف." : "Unable to rerun the spider."));
    } finally {
      setStarting(false);
    }
  };

  const startRun = async () => {
    if (!topicId || starting) return;
    const parsedSeedUrls = seedUrls.split("\n").map((item) => item.trim()).filter(Boolean);
    const parsedSearchTopics = searchTopics.split(",").map((item) => item.trim()).filter(Boolean);
    const parsedKeywords = targetKeywords.split(",").map((item) => item.trim()).filter(Boolean);
    if (parsedSeedUrls.length === 0 && parsedSearchTopics.length === 0 && parsedKeywords.length === 0) {
      setError(
        lang === "ar"
          ? "أدخل كلمات مفتاحية أو مواضيع بحث أو روابط بذرة على الأقل لبدء الزحف."
          : "Enter at least one search topic, keyword, or seed URL to start crawling.",
      );
      return;
    }
    setStarting(true);
    setError("");
    setMessage("");
    try {
      const payload = {
        topic_id: topicId,
        search_topics: parsedSearchTopics,
        target_keywords: parsedKeywords,
        seed_urls: parsedSeedUrls,
        relevance_threshold: relevanceThreshold,
        max_depth: maxDepth,
        proxy_enabled: proxyEnabled,
      };
      const result = await request<{ run_id: string; status: string; message: string }>("/api/v1/spider/run", token, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setActiveRunId(result.run_id);
      setMessage(result.message || (lang === "ar" ? "تم بدء دورة الزحف." : "Spider run started."));
      await loadRuns();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر بدء الزحف." : "Unable to start the spider."));
    } finally {
      setStarting(false);
    }
  };

  const injectTopic = async () => {
    if (!activeRun || !injectText.trim()) return;
    try {
      await request<SpiderRunStatus>("/api/v1/spider/add-topic", token, {
        method: "POST",
        body: JSON.stringify({
          run_id: activeRun.run_id,
          search_topics: [],
          target_keywords: injectText.split(",").map((item) => item.trim()).filter(Boolean),
        }),
      });
      setInjectText("");
      await loadRuns();
    } catch {
      setError(lang === "ar" ? "تعذر إضافة الكلمات إلى الدفعة الجارية." : "Unable to inject keywords into the run.");
    }
  };

  const stopRun = async () => {
    if (!activeRun || stopping) return;
    setStopping(true);
    setError("");
    try {
      await request<SpiderRunStatus>("/api/v1/spider/stop", token, {
        method: "POST",
        body: JSON.stringify({ run_id: activeRun.run_id }),
      });
      await loadRuns();
    } catch {
      setError(lang === "ar" ? "تعذر إيقاف التشغيل." : "Unable to stop the run.");
    } finally {
      setStopping(false);
    }
  };

  return (
    <div className="page-content automation-page spider-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">SPIDER ENGINE</p>
          <h1>{lang === "ar" ? "متابعة السبايدر" : "Spider monitor"}</h1>
          <p className="subhead">{lang === "ar" ? "شغّل زحفًا ديناميكيًا وتابع النتائج لحظيًا." : "Run dynamic crawls and track their results live."}</p>
        </div>
      </div>
      {error && <div className="data-error">{error}</div>}
      {message && <div className="connection-message">{message}</div>}
      <div className="automation-grid">
        <section className="panel automation-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">NEW RUN</p><h2>{lang === "ar" ? "تشغيل جديد" : "Start a new run"}</h2></div>
            <SpiderIcon size={20} color="var(--cyan)" />
          </div>
          <label>{lang === "ar" ? "الموضوع" : "Topic"}
            <select value={topicId ?? ""} onChange={(event) => setTopicId(Number(event.target.value))}>
              {topics.map((topic) => <option value={topic.id} key={topic.id}>{topic.title}</option>)}
            </select>
          </label>
          <label>{lang === "ar" ? "مواضيع البحث (مفصولة بفواصل)" : "Search topics (comma separated)"}
            <input value={searchTopics} onChange={(event) => setSearchTopics(event.target.value)} placeholder="اختراق بنكي, Ransomware" />
          </label>
          <label>{lang === "ar" ? "الكلمات المفتاحية (مفصولة بفواصل)" : "Target keywords (comma separated)"}
            <input value={targetKeywords} onChange={(event) => setTargetKeywords(event.target.value)} placeholder="بيانات, تسريب, CVE, breach" />
          </label>
          <label>{lang === "ar" ? "روابط البذرة (سطر لكل رابط، اختياري)" : "Seed URLs (one per line, optional)"}
            <textarea rows={3} value={seedUrls} onChange={(event) => setSeedUrls(event.target.value)} placeholder="https://example.com/news" />
            <small className="spider-hint">{lang === "ar" ? "اتركه فارغًا ليبحث السبايدر تلقائيًا في الإنترنت عن روابط غير محددة اعتمادًا على الكلمات المفتاحية." : "Leave empty to let the spider search the open web for unspecified links based on your keywords."}</small>
          </label>
          <div className="spider-form-row">
            <label>{lang === "ar" ? "حد الصلة %" : "Relevance %"}
              <input type="number" min={0} max={100} value={relevanceThreshold} onChange={(event) => setRelevanceThreshold(Number(event.target.value))} />
            </label>
            <label>{lang === "ar" ? "عمق الزحف" : "Max depth"}
              <input type="number" min={1} max={3} value={maxDepth} onChange={(event) => setMaxDepth(Number(event.target.value))} />
            </label>
            <label className="spider-checkbox">
              <input type="checkbox" checked={proxyEnabled} onChange={(event) => setProxyEnabled(event.target.checked)} />
              {lang === "ar" ? "تدوير البروكسي" : "Proxy rotation"}
            </label>
          </div>
          <button type="button" className="primary-button spider-start-button" disabled={starting || !topicId} onClick={() => void startRun()}>
            {starting ? <span className="loading-spinner" /> : <SpiderIcon size={15} />}
            {starting ? (lang === "ar" ? "جار البدء..." : "Starting...") : (lang === "ar" ? "بدء الزحف" : "Start crawl")}
          </button>
        </section>
        <section className="panel automation-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">LIVE RUN</p><h2>{lang === "ar" ? "التشغيل الحالي" : "Current run"}</h2></div>
            {activeRun && (
              <div className="spider-live-actions">
                <span className={`badge ${activeRun.status === "running" ? "badge-success" : "badge-neutral"}`}>{activeRun.status}</span>
                {activeRun.status === "running" && (
                  <button type="button" className="secondary-button spider-stop-button" disabled={stopping} onClick={() => void stopRun()}>
                    {stopping ? <span className="loading-spinner" /> : <X size={14} />}
                    {lang === "ar" ? "إيقاف" : "Stop"}
                  </button>
                )}
              </div>
            )}
          </div>
          {activeRun ? (
            <>
              <div className="automation-details">
                <div><span>{lang === "ar" ? "صفحات تم زحفها" : "Pages crawled"}</span><strong>{activeRun.pages_crawled}</strong></div>
                <div><span>{lang === "ar" ? "مقبولة" : "Accepted"}</span><strong>{activeRun.accepted}</strong></div>
                <div><span>{lang === "ar" ? "مرفوضة" : "Discarded"}</span><strong>{activeRun.discarded}</strong></div>
                <div><span>{lang === "ar" ? "أخطاء" : "Errors"}</span><strong>{activeRun.errors.length}</strong></div>
              </div>
              <div className="spider-keywords">
                <span>{lang === "ar" ? "الكلمات النشطة" : "Active keywords"}</span>
                <div className="spider-keyword-tags">
                  {activeRun.active_keywords.map((word) => <span className="badge badge-neutral" key={word}>{word}</span>)}
                </div>
              </div>
              {activeRun.status === "running" && (
                <div className="spider-inject">
                  <input value={injectText} onChange={(event) => setInjectText(event.target.value)} placeholder={lang === "ar" ? "إضافة كلمات للدفعة الجارية" : "Inject keywords into this run"} />
                  <button type="button" className="secondary-button" onClick={() => void injectTopic()}><Plus size={14} />{lang === "ar" ? "إضافة" : "Add"}</button>
                </div>
              )}
              {activeRun.errors.length > 0 && (
                <div className="automation-errors">
                  {activeRun.errors.map((item, index) => <div key={index}><AlertTriangle size={14} /><span>{item.url ?? "?"}</span><small>{item.error ?? ""}</small></div>)}
                </div>
              )}
            </>
          ) : <div className="empty-state">{lang === "ar" ? "لا يوجد تشغيل نشط حاليًا." : "No active run right now."}</div>}
        </section>
      </div>
      <section className="panel automation-panel spider-history">
        <div className="panel-heading">
          <div><p className="eyebrow">HISTORY</p><h2>{lang === "ar" ? "سجل التشغيلات" : "Run history"}</h2></div>
        </div>
        {runs.length ? (
          <div className="spider-history-list">
            {runs.map((run) => (
              <div className={`spider-history-row ${run.run_id === activeRun?.run_id ? "active" : ""}`} key={run.run_id} onClick={() => setActiveRunId(run.run_id)}>
                <span className={`automation-status-dot ${run.status === "running" ? "running" : "idle"}`} />
                <strong>{run.run_id}</strong>
                <span>
                  {run.accepted}/{run.pages_crawled} {lang === "ar" ? "مقبولة" : "accepted"}
                  <small>{lang === "ar" ? "المحددات" : "Parameters"}: {getRunParameterCount(run)}</small>
                </span>
                <span className="spider-history-actions" onClick={(event) => event.stopPropagation()}>
                  <button type="button" className="secondary-button" disabled={starting} onClick={() => void rerun(run)}>{lang === "ar" ? "إعادة تشغيل" : "Rerun"}</button>
                  <button type="button" className="secondary-button" onClick={() => applyRunParameters(run)}>{lang === "ar" ? "تعديل المحددات" : "Edit parameters"}</button>
                </span>
                <span className="badge badge-neutral">{run.status}</span>
              </div>
            ))}
          </div>
        ) : <div className="empty-state">{lang === "ar" ? "لا توجد تشغيلات بعد." : "No runs yet."}</div>}
      </section>
    </div>
  );
}

function Dashboard({ token, lang: language }: { token: string; lang: Lang }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [posts, setPosts] = useState<Post[]>([]);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [selectedTopicId, setSelectedTopicId] = useState<number | null>(null);
  const [selected, setSelected] = useState<Post | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [activityPage, setActivityPage] = useState(1);
  const [error, setError] = useState("");
  const activityPageSize = 5;
  const activityPageCount = Math.max(
    1,
    Math.ceil(posts.length / activityPageSize),
  );
  const visiblePosts = posts.slice(
    (activityPage - 1) * activityPageSize,
    activityPage * activityPageSize,
  );
  useEffect(() => {
    const load = () =>
      Promise.all([
        get<Stats>("/api/dashboard/stats", token),
        get<Post[]>("/api/dashboard/recent-activity", token),
        get<AiStatus>("/api/ai/status", token),
        get<Topic[]>("/api/v1/topics", token),
      ])
        .then(([s, p, ai, nextTopics]) => {
          setStats(s);
          const uniquePosts = p.filter((post, index, records) => {
            const identity = `${post.platform}|${post.author}|${post.post_url || post.content.trim()}`;
            return records.findIndex((candidate) => `${candidate.platform}|${candidate.author}|${candidate.post_url || candidate.content.trim()}` === identity) === index;
          });
          setPosts(uniquePosts);
          setAiStatus(ai);
          setTopics(nextTopics);
          setSelectedTopicId((current) => current ?? nextTopics[0]?.id ?? null);
          setActivityPage((current) => current);
        })
        .catch(() =>
          setError(
            language === "ar" ? "تعذر تحميل البيانات." : "Unable to load data.",
          ),
        );
    void load();
    const timer = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(timer);
  }, [token, language]);

  useEffect(() => {
    if (!selectedTopicId) return;
    const load = () =>
      get<{ alerts: AlertItem[]; summary?: AlertSummary }>(`/api/v1/analytics/topics/${selectedTopicId}/alerts`, token)
        .then((payload) => setAlerts(payload.alerts ?? []))
        .catch(() => setAlerts([]));
    void load();
    const timer = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(timer);
  }, [selectedTopicId, token]);

  const exportReport = async (format: "pdf" | "csv" | "json" | "xlsx") => {
    if (!selectedTopicId) return;
    const response = await fetch(`${API}/api/v1/analytics/topics/${selectedTopicId}/reports/executive-pdf?language=${language}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error(language === "ar" ? "تعذر تصدير التقرير." : "Unable to export the report.");
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `report_${selectedTopicId}.${format === "pdf" ? "pdf" : format}`;
    anchor.click();
    window.URL.revokeObjectURL(url);
  };

  const exportDataset = async (format: "csv" | "json" | "xlsx") => {
    if (!selectedTopicId) return;
    const response = await fetch(`${API}/api/topics/${selectedTopicId}/export/${format}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error(language === "ar" ? "تعذر تصدير البيانات." : "Unable to export dataset.");
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `topic_${selectedTopicId}_export.${format}`;
    anchor.click();
    window.URL.revokeObjectURL(url);
  };
  const cards = [
    [
      language === "ar" ? "إجمالي المنشورات" : "Total posts",
      stats?.total_posts ?? "—",
      Database,
    ],
    [
      language === "ar" ? "الإشارات المعلّمة" : "Flagged signals",
      stats?.flagged_posts ?? "—",
      ShieldCheck,
    ],
    [
      language === "ar" ? "مصادر RSS" : "RSS posts",
      stats?.posts_by_platform.rss ?? "—",
      Radio,
    ],
    [
      language === "ar" ? "شدة عالية" : "High severity",
      stats
        ? (stats.posts_by_severity.high ?? 0) +
          (stats.posts_by_severity.critical ?? 0)
        : "—",
      Activity,
    ],
  ] as const;
  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">{language === "ar" ? "النظام" : "System"}</p>
          <h1>{language === "ar" ? "نظرة عامة" : "Overview"}</h1>
          <p className="subhead">
            {language === "ar"
              ? "ملخص البيانات الحقيقية من قاعدة البيانات."
              : "Summary of live database data."}
          </p>
        </div>
      </div>
      {error && <div className="data-error">{error}</div>}
      <div className="metric-grid">
        {cards.map(([name, value, Icon]) => (
          <div className="metric-card" key={name}>
            <div className="metric-icon metric-cyan">
              <Icon size={19} />
            </div>
            <div className="metric-copy">
              <span>{name}</span>
              <strong>{value}</strong>
              <small>
                {language === "ar" ? "من قاعدة البيانات" : "from database"}
              </small>
            </div>
          </div>
        ))}
      </div>
      {aiStatus && (
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="panel-heading">
            <div>
              <p className="eyebrow">AI</p>
              <h2>{language === "ar" ? "حالة المحرك الذكي" : "AI engine status"}</h2>
            </div>
          </div>
          <div className="config-row">
            <span className="config-icon"><Settings2 size={15} /></span>
            <span>
              <strong>{aiStatus.enabled ? (language === "ar" ? "مفعّل" : "Enabled") : (language === "ar" ? "معطّل" : "Disabled")}</strong>
              <small>{aiStatus.provider === "disabled" ? (language === "ar" ? "الذكاء الاصطناعي غير متاح" : "AI unavailable") : aiStatus.model ?? aiStatus.provider}</small>
            </span>
          </div>
        </div>
      )}
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Reports</p>
            <h2>{language === "ar" ? "تقارير القيادة والتصدير" : "Executive reports & export"}</h2>
          </div>
        </div>
        <div className="config-row" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <select value={selectedTopicId ?? ""} onChange={(event) => setSelectedTopicId(Number(event.target.value))} disabled={!topics.length}>
            {topics.map((topic) => <option value={topic.id} key={topic.id}>{topic.title}</option>)}
          </select>
          <button type="button" className="primary-button" onClick={() => void exportReport("pdf")}>
            {language === "ar" ? "تصدير التقرير التنفيذي PDF" : "Export Executive PDF"}
          </button>
          <button type="button" className="secondary-button" onClick={() => void exportDataset("csv")}>CSV</button>
          <button type="button" className="secondary-button" onClick={() => void exportDataset("json")}>JSON</button>
          <button type="button" className="secondary-button" onClick={() => void exportDataset("xlsx")}>XLSX</button>
        </div>
      </div>
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Alerts</p>
            <h2>{language === "ar" ? "تنبيهات وحوادث" : "Alerts & incidents"}</h2>
          </div>
        </div>
        {alerts.length ? (
          <div className="config-list">
            {alerts.slice(0, 5).map((alert) => (
              <div className="config-row" key={alert.id}>
                <span className="config-icon">
                  <AlertTriangle size={15} />
                </span>
                <span>
                  <strong>{alert.title}</strong>
                  <small>{alert.description}</small>
                </span>
                <span className="badge badge-neutral">{alert.status}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">{language === "ar" ? "لا توجد تنبيهات نشطة." : "No active alerts."}</div>
        )}
      </div>
      <div className="dashboard-grid">
        <div className="panel chart-card">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">
                {language === "ar" ? "توزيع حقيقي" : "Live distribution"}
              </p>
              <h2>
                {language === "ar"
                  ? "المنشورات حسب المنصة"
                  : "Posts by platform"}
              </h2>
            </div>
          </div>
          <div className="data-bars">
            {stats ? (
              Object.entries(stats.posts_by_platform).map(
                ([platform, count]) => (
                  <div className="data-bar" key={platform}>
                    <span>{platform}</span>
                    <i>
                      <b
                        style={{
                          width: `${stats.total_posts ? Math.max(4, (count / stats.total_posts) * 100) : 0}%`,
                        }}
                      />
                    </i>
                    <strong>{count}</strong>
                  </div>
                ),
              )
            ) : (
              <p className="loading-text">{language === "ar" ? "جار التحميل..." : "Loading..."}</p>
            )}
          </div>
        </div>
        <div className="panel signal-panel">
          <p className="eyebrow">
            {language === "ar" ? "آخر البيانات" : "Latest data"}
          </p>
          <h2>
            {posts.length} {language === "ar" ? "منشورات" : "posts"}
          </h2>
          <p className="panel-note">
            {language === "ar"
              ? "منشورات محفوظة مؤخراً."
              : "Recently stored posts."}
          </p>
        </div>
      </div>
      <div className="panel recent-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">
              {language === "ar" ? "تدفق الإشارات" : "Signal stream"}
            </p>
            <h2>{language === "ar" ? "النشاط الأخير" : "Recent activity"}</h2>
          </div>
        </div>
        {visiblePosts.map((post) => (
          <button type="button" className="activity-row activity-row-button" key={post.id} onClick={() => setSelected(post)}>
            <span className="source-mark source-cyan">
              {post.platform[0]?.toUpperCase()}
            </span>
            <span className="activity-main">
              <strong>{toPlainText(post.title, 100) || toPlainText(post.content, 100)}</strong>
              <small>
                {post.author} ·{" "}
                {new Date(post.scraped_at).toLocaleString(
                  language === "ar" ? "ar-EG" : "en-US",
                )}
              </small>
            </span>
            <span className="badge badge-neutral">
              {post.severity_level || (language === "ar" ? "غير محلل" : "Unanalyzed")}
            </span>
          </button>
        ))}
        {posts.length > 0 && (
          <div className="pagination">
            <button
              className="secondary-button"
              disabled={activityPage === 1}
              onClick={() => setActivityPage(activityPage - 1)}
            >
              {language === "ar" ? "السابق" : "Previous"}
            </button>
            <span>
              {language === "ar" ? `صفحة ${activityPage} من ${activityPageCount}` : `Page ${activityPage} of ${activityPageCount}`}
            </span>
            <button
              className="secondary-button"
              disabled={activityPage === activityPageCount}
              onClick={() => setActivityPage(activityPage + 1)}
            >
              {language === "ar" ? "التالي" : "Next"}
            </button>
          </div>
        )}
      </div>
      {selected && (
        <PostDetailDialog
          post={selected}
          token={token}
          lang={language}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
type PostDetail = Post & {
  sentiment?: string | null;
  sentiment_score?: number | null;
  entities?: string[] | Record<string, unknown> | null;
  extracted_ocr_text?: string | null;
  video_transcript?: string | null;
  media_status?: "pending" | "completed" | "failed" | string;
};

const SEVERITY_METER: Record<string, number> = { low: 25, medium: 50, high: 75, critical: 100 };

function extractYoutubeVideoId(url: string | null | undefined): string | null {
  if (!url) return null;
  const match = url.match(/(?:v=|\/shorts\/|youtu\.be\/|\/embed\/)([A-Za-z0-9_-]{11})/);
  return match ? match[1] : null;
}

function resolveMediaUrl(url: string): string {
  return url.startsWith("/") ? `${API}${url}` : url;
}

// Scrapers (Reddit RSS in particular) store raw markup, which breaks card layouts.
function toPlainText(raw: string | null | undefined, limit?: number): string {
  if (!raw) return "";
  const stripped = raw
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/&#(\d+);/g, (_match, code: string) => String.fromCharCode(Number(code)))
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (limit === undefined || stripped.length <= limit) return stripped;
  return `${stripped.slice(0, limit).trimEnd()}…`;
}

function PostDetailDialog({
  post,
  token,
  lang,
  onClose,
}: {
  post: Post;
  token: string;
  lang: Lang;
  onClose: () => void;
}) {
  const [logs, setLogs] = useState<AuditRecord[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState<PostDetail>(post);
  const [tab, setTab] = useState<"original" | "ocr" | "transcript">("original");
  const [zoomImage, setZoomImage] = useState<string | null>(null);
  const loadLogs = () =>
    get<AuditRecord[]>(
      `/api/v1/audit-logs/topics/${post.topic_id}?limit=100`,
      token,
    )
      .then((records) =>
        setLogs(records.filter((record) => record.post_id === post.id)),
      )
      .catch(() => setError(lang === "ar" ? "تعذر تحميل نشاط الخبر." : "Unable to load news activity."));
  useEffect(() => {
    void loadLogs();
  }, [post.id, post.topic_id, token]);
  useEffect(() => {
    get<PostDetail>(`/api/v1/posts/${post.id}`, token)
      .then(setDetail)
      .catch(() => setDetail(post));
  }, [post.id, token]);
  const mark = async (field: "is_important" | "is_dangerous") => {
    setSaving(true);
    setError("");
    try {
      await request(
        `/api/v1/topics/${post.topic_id}/news/${post.id}/priority`,
        token,
        {
          method: "PATCH",
          body: JSON.stringify({
            is_important:
              field === "is_important" ? !post.is_important : post.is_important,
            is_dangerous:
              field === "is_dangerous" ? !post.is_dangerous : post.is_dangerous,
          }),
        },
      );
      await loadLogs();
    } catch {
      setError(lang === "ar" ? "تعذر تحديث أولوية الخبر." : "Unable to update the news priority.");
    } finally {
      setSaving(false);
    }
  };
  const entityTags: string[] = Array.isArray(detail.entities)
    ? (detail.entities as unknown[]).map((entry) => String(entry))
    : detail.entities && typeof detail.entities === "object"
      ? Object.keys(detail.entities as Record<string, unknown>)
      : [];
  const meterValue = SEVERITY_METER[detail.severity_level ?? ""] ?? 0;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="post-dialog" onClick={(event) => event.stopPropagation()}>
        <button className="icon-button" onClick={onClose}>
          <X size={18} />
        </button>
        <p className="eyebrow">{post.platform}</p>
        <h2>{post.title || (lang === "ar" ? "منشور بدون عنوان" : "Untitled post")}</h2>
        <p className="dialog-source">
          {post.author} · {new Date(post.scraped_at).toLocaleString(lang === "ar" ? "ar-EG" : "en-US")}
        </p>
        <div className="config-actions">
          <button
            className={`icon-button ${post.is_important ? "priority-active" : ""}`}
            title={lang === "ar" ? "مهم" : "Important"}
            aria-label={lang === "ar" ? "وضع علامة مهم" : "Mark as important"}
            disabled={saving}
            onClick={() => mark("is_important")}
          >
            <Star size={16} />
          </button>
          <button
            className={`icon-button ${post.is_dangerous ? "danger-active" : ""}`}
            title={lang === "ar" ? "خطير" : "Dangerous"}
            aria-label={lang === "ar" ? "وضع علامة خطير" : "Mark as dangerous"}
            disabled={saving}
            onClick={() => mark("is_dangerous")}
          >
            <AlertTriangle size={16} />
          </button>
        </div>
        {error && <div className="data-error">{error}</div>}
        {post.platform === "youtube" && extractYoutubeVideoId(post.post_url) ? (
          <div className="media-grid">
            <iframe
              className="video-embed"
              src={`https://www.youtube.com/embed/${extractYoutubeVideoId(post.post_url)}`}
              title="YouTube video player"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
        ) : post.media_urls?.length ? (
          <div className="media-grid">
            {post.media_urls.map((media, index) =>
              typeof media === "string" && /\.(mp4|webm|mov|mkv|m4a|mp3|wav)(\?|$)/i.test(media) ? (
                <video key={index} src={resolveMediaUrl(media)} controls />
              ) : typeof media === "string" ? (
                <img
                  key={index}
                  src={resolveMediaUrl(media)}
                  alt={lang === "ar" ? "وسائط الخبر" : "News media"}
                  onClick={() => setZoomImage(resolveMediaUrl(media))}
                  style={{ cursor: "zoom-in" }}
                />
              ) : null,
            )}
          </div>
        ) : (
          <div className="media-empty">{lang === "ar" ? "لا توجد صورة أو فيديو لهذا الخبر." : "No image or video for this news item."}</div>
        )}
        <div className="config-tabs">
          <button className={tab === "original" ? "selected" : ""} onClick={() => setTab("original")}>
            {lang === "ar" ? "النص الأصلي" : "Original text"}
          </button>
          <button className={tab === "ocr" ? "selected" : ""} onClick={() => setTab("ocr")}>
            {lang === "ar" ? "نص الصور (OCR)" : "Image text (OCR)"}
          </button>
          <button className={tab === "transcript" ? "selected" : ""} onClick={() => setTab("transcript")}>
            {lang === "ar" ? "نص الصوت/الفيديو" : "Audio/video transcript"}
          </button>
        </div>
        <p className="dialog-content">
          {tab === "original"
            ? post.content
            : tab === "ocr"
              ? (detail.extracted_ocr_text || (detail.media_status === "pending" ? (lang === "ar" ? "جارٍ المعالجة..." : "Processing...") : (lang === "ar" ? "لا يوجد نص مستخرج من الصور." : "No text extracted from images.")))
              : (detail.video_transcript || (detail.media_status === "pending" ? (lang === "ar" ? "جارٍ المعالجة..." : "Processing...") : (lang === "ar" ? "لا يوجد نص مفرغ من الصوت/الفيديو." : "No transcript available from audio/video.")))}
        </p>
        <div className="panel dialog-analytics">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Combined analytics</p>
              <h3>{lang === "ar" ? "تحليل موحّد للنص والوسائط" : "Combined text & media analysis"}</h3>
            </div>
            <Activity size={18} />
          </div>
          <div className="config-row">
            <span>
              <strong>{lang === "ar" ? "المشاعر" : "Sentiment"}</strong>
              <small>{detail.sentiment ?? (lang === "ar" ? "غير محدد" : "Undetermined")}{detail.sentiment_score != null ? ` (${detail.sentiment_score})` : ""}</small>
            </span>
            <span className="badge badge-neutral">{detail.media_status ?? "pending"}</span>
          </div>
          <div className="severity-meter">
            <div className="severity-meter-track">
              <div className="severity-meter-fill" style={{ width: `${meterValue}%` }} />
            </div>
            <small>{detail.severity_level ?? (lang === "ar" ? "غير محلل" : "Unanalyzed")}</small>
          </div>
          {entityTags.length > 0 && (
            <div className="entity-tags">
              {entityTags.map((tag) => (
                <span className="badge badge-neutral" key={tag}>{tag}</span>
              ))}
            </div>
          )}
        </div>
        {post.post_url && (
          <a
            className="wide-ghost"
            href={post.post_url}
            target="_blank"
            rel="noreferrer"
          >
            {lang === "ar" ? "فتح المصدر الأصلي" : "Open original source"} <ArrowUpRight size={15} />
          </a>
        )}
        <div className="dialog-activity">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Activity</p>
              <h3>{lang === "ar" ? "نشاط المستخدمين" : "User activity"}</h3>
            </div>
            <ShieldCheck size={18} />
          </div>
          {logs.length ? (
            logs.map((log) => (
              <div className="config-row" key={log.id}>
                <span className="config-icon">
                  <Check size={15} />
                </span>
                <span>
                  <strong>{log.action}</strong>
                  <small>
                    User #{log.user_id ?? "-"} ·{" "}
                    {log.details
                      ? Object.entries(log.details)
                          .filter(([, value]) => value)
                          .map(([key]) => key)
                          .join(lang === "ar" ? "، " : ", ")
                      : ""}
                  </small>
                </span>
                <small>
                  {new Date(log.created_at).toLocaleString(lang === "ar" ? "ar-EG" : "en-US")}
                </small>
              </div>
            ))
          ) : (
            <div className="empty-state">{lang === "ar" ? "لا يوجد نشاط مسجل لهذا الخبر." : "No recorded activity for this news item."}</div>
          )}
        </div>
      </div>
      {zoomImage && (
        <div className="modal-backdrop image-lightbox" onClick={() => setZoomImage(null)}>
          <img src={zoomImage} alt={lang === "ar" ? "تكبير الصورة" : "Zoomed image"} onClick={(event) => event.stopPropagation()} />
        </div>
      )}
    </div>
  );
}

function Feed({ token, lang }: { token: string; lang: Lang }) {
  const [posts, setPosts] = useState<Post[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [range, setRange] = useState("day");
  const [keyword, setKeyword] = useState("");
  const [topicFilter, setTopicFilter] = useState("all");
  const [websiteFilter, setWebsiteFilter] = useState("all");
  const [selected, setSelected] = useState<Post | null>(null);
  const [checkedIds, setCheckedIds] = useState<Set<number>>(new Set());
  const [exporting, setExporting] = useState<"pdf" | "csv" | "json" | "xlsx" | null>(null);
  const [exportError, setExportError] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const [filtered, setFiltered] = useState<Post[]>([]);
  const [viewMode, setViewMode] = useState<"table" | "kanban">("table");
  const [feedPage, setFeedPage] = useState(1);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);
  const [analysisError, setAnalysisError] = useState("");
  const feedPageSize = 6;
  const feedPageCount = Math.max(1, Math.ceil(filtered.length / feedPageSize));
  const visibleFeedPosts = filtered.slice(
    (feedPage - 1) * feedPageSize,
    feedPage * feedPageSize,
  );
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    const load = () =>
      get<Post[]>("/api/data/posts/latest?limit=500", token)
        .then(setPosts)
        .catch(() => setPosts([]));
    void load();
    const timer = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(timer);
  }, [token]);
  useEffect(() => {
    void get<Topic[]>("/api/v1/topics", token)
      .then(setTopics)
      .catch(() => setTopics([]));
  }, [token]);
  const durations: Record<string, number> = {
    hour: 3600000,
    day: 86400000,
    week: 604800000,
    month: 2592000000,
    days90: 7776000000,
    year: 31536000000,
  };
  const getPostWebsite = (post: Post) => {
    if (!post.post_url) return post.platform;
    try {
      return new URL(post.post_url).hostname.replace(/^www\./, "");
    } catch {
      return post.platform;
    }
  };
  const websiteOptions = useMemo(
    () => Array.from(new Set(posts.map(getPostWebsite).filter(Boolean))).sort((a, b) => a.localeCompare(b)),
    [posts],
  );
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const search = keyword.toLocaleLowerCase();
      setFiltered(
        posts.filter(
          (post) => {
            const scrapedAt = new Date(post.scraped_at).getTime();
            const age = now - scrapedAt;
            return Number.isFinite(scrapedAt) &&
              age >= 0 &&
              age <= durations[range] &&
              (topicFilter === "all" || post.topic_id === Number(topicFilter)) &&
              (websiteFilter === "all" || getPostWebsite(post) === websiteFilter) &&
              `${post.title ?? ""} ${post.content} ${post.author} ${post.platform}`
                .toLocaleLowerCase()
                .includes(search);
          },
        ),
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, [posts, now, range, keyword, topicFilter, websiteFilter]);
  // Only jump back to page 1 when the user changes a filter, not on every background refresh.
  useEffect(() => {
    setFeedPage(1);
  }, [range, keyword, topicFilter, websiteFilter]);
  useEffect(() => {
    setFeedPage((current) => Math.min(current, feedPageCount));
  }, [feedPageCount]);
  const ranges = [
    ["hour", lang === "ar" ? "آخر ساعة" : "Last hour"],
    ["day", lang === "ar" ? "اليوم" : "Today"],
    ["week", lang === "ar" ? "الأسبوع" : "This week"],
    ["month", lang === "ar" ? "الشهر" : "This month"],
    ["days90", lang === "ar" ? "90 يوماً" : "90 days"],
    ["year", lang === "ar" ? "السنة" : "This year"],
  ];
  const toggleChecked = (id: number) =>
    setCheckedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const clearSelection = () => setCheckedIds(new Set());
  const analyzePost = async (postId: number) => {
    if (analyzingId !== null) return;
    setAnalyzingId(postId);
    setAnalysisError("");
    try {
      const result = await request<{ processed: number; analyzed: number; failed: number }>(`/api/ai/analyze/${postId}`, token, {
        method: "POST",
      });
      if (result.failed) {
        setAnalysisError(lang === "ar" ? "تعذر تحليل هذا الخبر." : "Unable to analyze this news item.");
      } else {
        await get<Post[]>("/api/data/posts/latest?limit=500", token).then(setPosts);
      }
    } catch (cause) {
      setAnalysisError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر تحليل هذا الخبر." : "Unable to analyze this news item."));
    } finally {
      setAnalyzingId(null);
    }
  };
  const exportSelected = async (format: "pdf" | "csv" | "json" | "xlsx") => {
    if (checkedIds.size === 0 || exporting) return;
    setExporting(format);
    setExportError("");
    try {
      const response = await fetch(`${API}/api/v1/posts/export/${format}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ post_ids: Array.from(checkedIds), lang }),
      });
      if (!response.ok) throw new ApiError(response.status);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `selected_posts_export.${format}`;
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (cause) {
      setExportError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر تصدير السجلات المحددة." : "Unable to export the selected records."));
    } finally {
      setExporting(null);
    }
  };
  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">{lang === "ar" ? "بيانات مباشرة" : "Live data"}</p>
          <h1>{lang === "ar" ? "موجز الاستخبارات" : "Intelligence feed"}</h1>
          <p className="subhead">{lang === "ar" ? `${filtered.length} خبر مطابق للفلاتر الحالية.` : `${filtered.length} items match the current filters.`}</p>
        </div>
      </div>
      {analysisError && <div className="data-error">{analysisError}</div>}
      <div className="feed-filters">
        <label className="search-field">
          <Search size={17} />
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder={lang === "ar" ? "فلترة بالكلمات المفتاحية" : "Filter by keywords"}
          />
        </label>
        <select
          value={range}
          onChange={(event) => setRange(event.target.value)}
        >
          {ranges.map(([value, label]) => (
            <option value={value} key={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          value={topicFilter}
          onChange={(event) => setTopicFilter(event.target.value)}
          aria-label={lang === "ar" ? "فلترة بالموضوع" : "Filter by topic"}
        >
          <option value="all">{lang === "ar" ? "كل المواضيع" : "All topics"}</option>
          {topics.map((topic) => (
            <option value={String(topic.id)} key={topic.id}>
              {topic.title}
            </option>
          ))}
        </select>
        <select
          value={websiteFilter}
          onChange={(event) => setWebsiteFilter(event.target.value)}
          aria-label={lang === "ar" ? "فلترة بالموقع" : "Filter by website"}
        >
          <option value="all">{lang === "ar" ? "كل المواقع" : "All websites"}</option>
          {websiteOptions.map((website) => (
            <option value={website} key={website}>
              {website}
            </option>
          ))}
        </select>
        <div className="view-toggle" aria-label={lang === "ar" ? "طريقة عرض الأخبار" : "News view mode"}>
          <button
            type="button"
            className={viewMode === "table" ? "selected" : ""}
            onClick={() => setViewMode("table")}
            aria-label={lang === "ar" ? "عرض جدولي" : "Table view"}
            title={lang === "ar" ? "عرض جدولي" : "Table view"}
          >
            <List size={16} />
          </button>
          <button
            type="button"
            className={viewMode === "kanban" ? "selected" : ""}
            onClick={() => setViewMode("kanban")}
            aria-label={lang === "ar" ? "عرض كانبان" : "Kanban view"}
            title={lang === "ar" ? "عرض كانبان" : "Kanban view"}
          >
            <LayoutGrid size={16} />
          </button>
        </div>
      </div>
      {checkedIds.size > 0 && (
        <div className="feed-export-toolbar">
          <span>{lang === "ar" ? `${checkedIds.size} محدد` : `${checkedIds.size} selected`}</span>
          <div className="feed-export-actions">
            <button type="button" className="secondary-button" disabled={exporting !== null} onClick={() => void exportSelected("pdf")}>
              {exporting === "pdf" ? <span className="loading-spinner" /> : <FileText size={14} />} PDF
            </button>
            <button type="button" className="secondary-button" disabled={exporting !== null} onClick={() => void exportSelected("csv")}>
              {exporting === "csv" ? <span className="loading-spinner" /> : <FileText size={14} />} CSV
            </button>
            <button type="button" className="secondary-button" disabled={exporting !== null} onClick={() => void exportSelected("json")}>
              {exporting === "json" ? <span className="loading-spinner" /> : <FileText size={14} />} JSON
            </button>
            <button type="button" className="secondary-button" disabled={exporting !== null} onClick={() => void exportSelected("xlsx")}>
              {exporting === "xlsx" ? <span className="loading-spinner" /> : <FileText size={14} />} XLSX
            </button>
          </div>
          <button type="button" className="text-button" onClick={clearSelection}>
            {lang === "ar" ? "إلغاء التحديد" : "Clear selection"}
          </button>
        </div>
      )}
      {exportError && <div className="data-error">{exportError}</div>}
      {viewMode === "table" ? (
        <div className="feed-table-wrap">
          <table className="feed-table">
            <thead>
              <tr>
                <th>{lang === "ar" ? "تحديد" : "Select"}</th>
                <th>{lang === "ar" ? "المنصة" : "Platform"}</th>
                <th>{lang === "ar" ? "الخبر" : "News"}</th>
                <th>{lang === "ar" ? "الكاتب" : "Author"}</th>
                <th>{lang === "ar" ? "الخطورة" : "Severity"}</th>
                <th>{lang === "ar" ? "التاريخ" : "Date"}</th>
                <th>{lang === "ar" ? "إجراء" : "Action"}</th>
              </tr>
            </thead>
            <tbody>
              {visibleFeedPosts.map((post) => (
                <tr key={post.id} className={checkedIds.has(post.id) ? "selected" : ""} onClick={() => setSelected(post)}>
                  <td onClick={(event) => event.stopPropagation()}>
                    <input type="checkbox" checked={checkedIds.has(post.id)} onChange={() => toggleChecked(post.id)} aria-label={lang === "ar" ? "تحديد هذا الخبر للتصدير" : "Select this news item for export"} />
                  </td>
                  <td><span className="table-platform"><Globe2 size={14} />{post.platform}</span></td>
                  <td><strong>{post.title || post.content.slice(0, 120)}</strong><small>{post.content.slice(0, 150)}</small></td>
                  <td>{post.author}</td>
                  <td><span className={`badge badge-${post.severity_level || "neutral"}`}>{post.severity_level || (lang === "ar" ? "غير محلل" : "Unanalyzed")}</span></td>
                  <td>{new Date(post.scraped_at).toLocaleString(lang === "ar" ? "ar-EG" : "en-US")}</td>
                  <td onClick={(event) => event.stopPropagation()}>
                    {!post.severity_level && (
                      <button type="button" className="icon-button" title={lang === "ar" ? "تحليل هذا الخبر" : "Analyze this news item"} aria-label={lang === "ar" ? "تحليل هذا الخبر" : "Analyze this news item"} disabled={analyzingId !== null} onClick={() => void analyzePost(post.id)}>
                        {analyzingId === post.id ? <span className="loading-spinner" /> : <Sparkles size={15} />}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="kanban-board">
          {visibleFeedPosts.map((post) => {
            const severity = (post.severity_level || "unanalyzed").toLowerCase();
            return (
              <article className={`kanban-card severity-${severity} ${checkedIds.has(post.id) ? "selected" : ""}`} key={post.id}>
                <div className="kanban-card-top"><span>{post.platform}</span><label onClick={(event) => event.stopPropagation()}><input type="checkbox" checked={checkedIds.has(post.id)} onChange={() => toggleChecked(post.id)} aria-label={lang === "ar" ? "تحديد هذا الخبر للتصدير" : "Select this news item for export"} /></label></div>
                <button type="button" onClick={() => setSelected(post)}><strong>{toPlainText(post.title, 90) || toPlainText(post.content, 90)}</strong><p>{toPlainText(post.content, 180)}</p></button>
                <div className="kanban-card-footer"><small>{post.author} · {new Date(post.scraped_at).toLocaleDateString(lang === "ar" ? "ar-EG" : "en-US")}</small><span className="severity-label">{post.severity_level || (lang === "ar" ? "غير محلل" : "Unanalyzed")}</span>{!post.severity_level && <button type="button" className="icon-button" title={lang === "ar" ? "تحليل هذا الخبر" : "Analyze this news item"} aria-label={lang === "ar" ? "تحليل هذا الخبر" : "Analyze this news item"} disabled={analyzingId !== null} onClick={(event) => { event.stopPropagation(); void analyzePost(post.id); }}>{analyzingId === post.id ? <span className="loading-spinner" /> : <Sparkles size={15} />}</button>}</div>
              </article>
            );
          })}
        </div>
      )}
      {filtered.length > 0 && (
        <div className="pagination">
          <button
            className="secondary-button"
            disabled={feedPage === 1}
            onClick={() => setFeedPage((page) => page - 1)}
          >
            {lang === "ar" ? "السابق" : "Previous"}
          </button>
          <span>{lang === "ar" ? `صفحة ${feedPage} من ${feedPageCount}` : `Page ${feedPage} of ${feedPageCount}`}</span>
          <button
            className="secondary-button"
            disabled={feedPage === feedPageCount}
            onClick={() => setFeedPage((page) => page + 1)}
          >
            {lang === "ar" ? "التالي" : "Next"}
          </button>
        </div>
      )}
      {selected && (
        <PostDetailDialog
          post={selected}
          token={token}
          lang={lang}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
function statusLabel(status: string | undefined, lang: Lang) {
  const map = lang === "ar"
    ? { pending: "قيد المراجعة", approved: "تمت الموافقة", rejected: "مرفوض" }
    : { pending: "Pending", approved: "Approved", rejected: "Rejected" };
  return map[(status ?? "pending") as "pending" | "approved" | "rejected"] ?? status;
}

function ApprovalsPanel({ token, lang }: { token: string; lang: Lang }) {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicId, setTopicId] = useState<number | null>(null);
  const [summary, setSummary] = useState<ApprovalsSummary>({ sources: [], keywords: [] });
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = (selected = topicId) => {
    if (!selected) return;
    void get<ApprovalsSummary>(`/api/v1/topics/${selected}/approvals`, token)
      .then(setSummary)
      .catch((cause) => {
        setSummary({ sources: [], keywords: [] });
        setError(cause instanceof ApiError ? cause.message : (lang === "ar" ? "تعذر تحميل الطلبات." : "Unable to load approvals."));
      });
  };
  useEffect(() => {
    void get<Topic[]>("/api/v1/topics", token)
      .then((items) => {
        setTopics(items);
        setTopicId((current) => current ?? items[0]?.id ?? null);
      })
      .catch(() => setTopics([]));
  }, [token]);
  useEffect(() => { load(); }, [topicId, token]);

  const decide = async (kind: "sources" | "keywords", item: Item, decision: "approved" | "rejected") => {
    setBusyId(item.id);
    try {
      await request<Item>(`/api/v1/approvals/${kind}/${item.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({ status: decision }),
      });
      load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : (lang === "ar" ? "تعذر تحديث الطلب." : "Unable to update proposal."));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">{lang === "ar" ? "الموافقات" : "APPROVALS"}</p>
          <h1>{lang === "ar" ? "طلبات المراقبين المعلقة" : "Pending observer requests"}</h1>
          <p className="subhead">
            {lang === "ar"
              ? "راجع مقترحات الروابط والكلمات المفتاحية قبل تفعيلها في عملية الجمع."
              : "Review proposed sources and keywords before they activate in the scraping pipeline."}
          </p>
        </div>
        <select value={topicId ?? ""} onChange={(event) => setTopicId(Number(event.target.value))}>
          {topics.map((topic) => (
            <option value={topic.id} key={topic.id}>{topic.title}</option>
          ))}
        </select>
      </div>
      {error && <div className="data-error">{error}</div>}
      <div className="panel">
        <div className="panel-heading">
          <h2>{lang === "ar" ? "مصادر مقترحة" : "Proposed sources"}</h2>
        </div>
        <div className="config-list">
          {summary.sources.length === 0 && (
            <div className="empty-state">{lang === "ar" ? "لا توجد طلبات معلقة." : "No pending proposals."}</div>
          )}
          {summary.sources.map((item) => (
            <div className="config-row" key={item.id}>
              <span className="config-icon">{item.platform?.[0]?.toUpperCase() ?? "#"}</span>
              <span>
                <strong>{item.name}</strong>
                <small>{item.url_or_handle}</small>
              </span>
              <span className="config-actions">
                <button className="icon-button" title={lang === "ar" ? "قبول" : "Approve"} disabled={busyId === item.id} onClick={() => decide("sources", item, "approved")}>
                  <Check size={15} />
                </button>
                <button className="icon-button danger-button" title={lang === "ar" ? "رفض" : "Reject"} disabled={busyId === item.id} onClick={() => decide("sources", item, "rejected")}>
                  <X size={15} />
                </button>
              </span>
            </div>
          ))}
        </div>
      </div>
      <div className="panel">
        <div className="panel-heading">
          <h2>{lang === "ar" ? "كلمات مفتاحية مقترحة" : "Proposed keywords"}</h2>
        </div>
        <div className="config-list">
          {summary.keywords.length === 0 && (
            <div className="empty-state">{lang === "ar" ? "لا توجد طلبات معلقة." : "No pending proposals."}</div>
          )}
          {summary.keywords.map((item) => (
            <div className="config-row" key={item.id}>
              <span className="config-icon">#</span>
              <span>
                <strong>{item.word_or_phrase}</strong>
                <small>{item.category}</small>
              </span>
              <span className="config-actions">
                <button className="icon-button" title={lang === "ar" ? "قبول" : "Approve"} disabled={busyId === item.id} onClick={() => decide("keywords", item, "approved")}>
                  <Check size={15} />
                </button>
                <button className="icon-button danger-button" title={lang === "ar" ? "رفض" : "Reject"} disabled={busyId === item.id} onClick={() => decide("keywords", item, "rejected")}>
                  <X size={15} />
                </button>
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ProposalsPanel({ token, lang }: { token: string; lang: Lang }) {
  const [tab, setTab] = useState<"submit" | "mine">("submit");
  const [kind, setKind] = useState<"sources" | "keywords">("sources");
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicId, setTopicId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [platform, setPlatform] = useState("rss");
  const [value, setValue] = useState("");
  const [mine, setMine] = useState<ApprovalsSummary>({ sources: [], keywords: [] });
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void get<Topic[]>("/api/v1/topics", token)
      .then((items) => {
        setTopics(items);
        setTopicId((current) => current ?? items[0]?.id ?? null);
      })
      .catch(() => setTopics([]));
  }, [token]);

  const loadMine = () => {
    if (!topicId) return;
    void get<ApprovalsSummary>(`/api/v1/topics/${topicId}/my-proposals`, token)
      .then(setMine)
      .catch(() => setMine({ sources: [], keywords: [] }));
  };
  useEffect(() => { if (tab === "mine") loadMine(); }, [tab, topicId]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!topicId) return;
    setError("");
    setMessage("");
    const body = kind === "sources"
      ? { name, platform, url_or_handle: value, target_type: "url", is_active: true }
      : { word_or_phrase: value, category: "general", is_active: true };
    try {
      await request<Item>(`/api/v1/topics/${topicId}/proposals/${kind}`, token, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setName("");
      setValue("");
      setMessage(lang === "ar" ? "تم إرسال المقترح للمراجعة." : "Proposal submitted for review.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : (lang === "ar" ? "تعذر إرسال المقترح." : "Unable to submit proposal."));
    }
  };

  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">{lang === "ar" ? "المقترحات" : "PROPOSALS"}</p>
          <h1>{lang === "ar" ? "تقديم مصدر أو كلمة مفتاحية" : "Submit a source or keyword"}</h1>
          <p className="subhead">
            {lang === "ar"
              ? "سيتم مراجعة المقترحات من قبل مدير الموضوع قبل تفعيلها."
              : "Proposals are reviewed by the topic manager before activation."}
          </p>
        </div>
        <select value={topicId ?? ""} onChange={(event) => setTopicId(Number(event.target.value))}>
          {topics.map((topic) => (
            <option value={topic.id} key={topic.id}>{topic.title}</option>
          ))}
        </select>
      </div>
      <div className="config-tabs">
        <button className={tab === "submit" ? "selected" : ""} onClick={() => setTab("submit")}>
          {lang === "ar" ? "تقديم مقترح" : "Submit proposal"}
        </button>
        <button className={tab === "mine" ? "selected" : ""} onClick={() => setTab("mine")}>
          {lang === "ar" ? "مقترحاتي" : "My submissions"}
        </button>
      </div>
      {tab === "submit" ? (
        <form className="panel" onSubmit={submit}>
          {error && <div className="data-error">{error}</div>}
          {message && <div className="connection-message">{message}</div>}
          <div className="config-tabs">
            <button type="button" className={kind === "sources" ? "selected" : ""} onClick={() => setKind("sources")}>
              {lang === "ar" ? "مصدر" : "Source"}
            </button>
            <button type="button" className={kind === "keywords" ? "selected" : ""} onClick={() => setKind("keywords")}>
              {lang === "ar" ? "كلمة مفتاحية" : "Keyword"}
            </button>
          </div>
          {kind === "sources" ? (
            <>
              <label>
                {lang === "ar" ? "الاسم" : "Name"}
                <input value={name} onChange={(event) => setName(event.target.value)} required />
              </label>
              <label>
                {lang === "ar" ? "المنصة" : "Platform"}
                <select value={platform} onChange={(event) => setPlatform(event.target.value)}>
                  <option value="rss">RSS</option>
                  <option value="telegram">Telegram</option>
                  <option value="facebook">Facebook</option>
                  <option value="reddit">Reddit</option>
                  <option value="youtube">YouTube</option>
                  <option value="x">X (Twitter)</option>
                </select>
              </label>
              <label>
                {lang === "ar" ? "الرابط أو المعرف" : "URL or handle"}
                <input value={value} onChange={(event) => setValue(event.target.value)} required />
              </label>
            </>
          ) : (
            <label>
              {lang === "ar" ? "الكلمة أو العبارة" : "Word or phrase"}
              <input value={value} onChange={(event) => setValue(event.target.value)} required />
            </label>
          )}
          <button className="primary-button" type="submit">
            <Plus size={16} /> {lang === "ar" ? "إرسال المقترح" : "Submit proposal"}
          </button>
        </form>
      ) : (
        <div className="panel config-list">
          {[...mine.sources, ...mine.keywords].length === 0 && (
            <div className="empty-state">{lang === "ar" ? "لا توجد مقترحات مقدّمة بعد." : "No submissions yet."}</div>
          )}
          {mine.sources.map((item) => (
            <div className="config-row" key={`s-${item.id}`}>
              <span className="config-icon">{item.platform?.[0]?.toUpperCase() ?? "#"}</span>
              <span>
                <strong>{item.name}</strong>
                <small>{item.url_or_handle}</small>
              </span>
              <span className="badge badge-neutral">{statusLabel(item.approval_status, lang)}</span>
            </div>
          ))}
          {mine.keywords.map((item) => (
            <div className="config-row" key={`k-${item.id}`}>
              <span className="config-icon">#</span>
              <span>
                <strong>{item.word_or_phrase}</strong>
                <small>{item.category}</small>
              </span>
              <span className="badge badge-neutral">{statusLabel(item.approval_status, lang)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function GraphPage({ token, request, lang }: { token: string; request: <T,>(path: string, init?: RequestInit) => Promise<T>; lang: Lang }) {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicId, setTopicId] = useState<number | null>(null);
  useEffect(() => {
    void get<Topic[]>("/api/v1/topics", token)
      .then((items) => {
        setTopics(items);
        setTopicId((current) => current ?? items[0]?.id ?? null);
      })
      .catch(() => setTopics([]));
  }, [token]);
  if (!topicId) {
    return (
      <div className="page-content">
        <div className="panel placeholder-page">
          <p>{lang === "ar" ? "لا توجد مواضيع متاحة." : "No topics available."}</p>
        </div>
      </div>
    );
  }
  return (
    <div className="page-content graph-page">
      <div className="page-header">
        <div />
        <select value={topicId} onChange={(event) => setTopicId(Number(event.target.value))}>
          {topics.map((topic) => (
            <option value={topic.id} key={topic.id}>{topic.title}</option>
          ))}
        </select>
      </div>
      <PropagationGraphView topicId={topicId} request={request} lang={lang} />
    </div>
  );
}

type ActivityEntry = { id: number; action: string; entity_type: string; created_at: string };
type ProfileData = {
  id: number;
  email: string;
  full_name: string;
  role: string;
  avatar_url: string | null;
  job_title: string | null;
  last_login_at: string | null;
  password_changed_at: string;
  totp_enabled: boolean;
  two_factor_eligible: boolean;
  activity_score: "high" | "medium" | "low";
  activity_count_30d: number;
  recent_activity: ActivityEntry[];
};

function ActivityBadge({ score, lang }: { score: string; lang: Lang }) {
  const labelMap = lang === "ar" ? { high: "نشاط مرتفع", medium: "نشاط متوسط", low: "نشاط منخفض" } : { high: "High activity", medium: "Medium activity", low: "Low activity" };
  return <span className={`badge badge-${score === "high" ? "success" : score === "medium" ? "medium" : "neutral"}`}>{labelMap[score as "high" | "medium" | "low"] ?? score}</span>;
}

function ProfilePage({ token, lang }: { token: string; lang: Lang }) {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [fullName, setFullName] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [twoFactorModal, setTwoFactorModal] = useState(false);
  const [qrCode, setQrCode] = useState("");
  const [secret, setSecret] = useState("");
  const [twoFactorCode, setTwoFactorCode] = useState("");

  const load = () => {
    void get<ProfileData>("/api/v1/profile/me", token)
      .then((data) => {
        setProfile(data);
        setFullName(data.full_name);
        setAvatarUrl(data.avatar_url ?? "");
        setJobTitle(data.job_title ?? "");
      })
      .catch(() => setError(lang === "ar" ? "تعذر تحميل الملف الشخصي." : "Unable to load profile."));
  };
  useEffect(() => { load(); }, [token]);

  const saveProfile = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      await request<ProfileData>("/api/v1/profile/me", token, {
        method: "PATCH",
        body: JSON.stringify({ full_name: fullName, avatar_url: avatarUrl || null, job_title: jobTitle || null }),
      });
      setMessage(lang === "ar" ? "تم حفظ الملف الشخصي." : "Profile saved.");
      load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : (lang === "ar" ? "تعذر حفظ الملف الشخصي." : "Unable to save profile."));
    }
  };

  const changePassword = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      await request<void>("/api/v1/profile/change-password", token, {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setCurrentPassword("");
      setNewPassword("");
      setMessage(lang === "ar" ? "تم تحديث كلمة المرور." : "Password updated.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : (lang === "ar" ? "تعذر تحديث كلمة المرور." : "Unable to update password."));
    }
  };

  const startTwoFactorSetup = async () => {
    setError("");
    try {
      const data = await request<{ secret: string; qr_code_base64: string }>("/api/v1/profile/2fa/setup", token, { method: "POST" });
      setSecret(data.secret);
      setQrCode(data.qr_code_base64);
      setTwoFactorModal(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : (lang === "ar" ? "تعذر بدء إعداد التحقق الثنائي." : "Unable to start 2FA setup."));
    }
  };

  const confirmTwoFactor = async () => {
    setError("");
    try {
      await request<void>("/api/v1/profile/2fa/enable", token, { method: "POST", body: JSON.stringify({ code: twoFactorCode }) });
      setTwoFactorModal(false);
      setTwoFactorCode("");
      setMessage(lang === "ar" ? "تم تفعيل التحقق الثنائي." : "2FA enabled.");
      load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : (lang === "ar" ? "رمز التحقق غير صحيح." : "Invalid verification code."));
    }
  };

  const disableTwoFactor = async () => {
    setError("");
    try {
      await request<void>("/api/v1/profile/2fa/disable", token, { method: "POST" });
      setMessage(lang === "ar" ? "تم إيقاف التحقق الثنائي." : "2FA disabled.");
      load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : (lang === "ar" ? "تعذر إيقاف التحقق الثنائي." : "Unable to disable 2FA."));
    }
  };

  if (!profile) {
    return <div className="page-content"><div className="panel placeholder-page">{lang === "ar" ? "جارٍ التحميل..." : "Loading..."}</div></div>;
  }

  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">{lang === "ar" ? "الحساب" : "ACCOUNT"}</p>
          <h1>{lang === "ar" ? "الملف الشخصي والأمان" : "Profile & Security"}</h1>
          <p className="subhead">{profile.email} · {profile.role}</p>
        </div>
        <ActivityBadge score={profile.activity_score} lang={lang} />
      </div>
      {error && <div className="data-error">{error}</div>}
      {message && <div className="connection-message">{message}</div>}
      <div className="dashboard-grid">
        <form className="panel chart-card" onSubmit={saveProfile}>
          <div className="panel-heading">
            <h2>{lang === "ar" ? "معلومات الملف الشخصي" : "Profile info"}</h2>
            <UserCog size={18} />
          </div>
          <label>
            {lang === "ar" ? "الاسم الكامل" : "Full name"}
            <input value={fullName} onChange={(event) => setFullName(event.target.value)} required />
          </label>
          <label>
            {lang === "ar" ? "المسمى الوظيفي" : "Job title"}
            <input value={jobTitle} onChange={(event) => setJobTitle(event.target.value)} />
          </label>
          <label>
            {lang === "ar" ? "رابط الصورة الرمزية" : "Avatar URL"}
            <input value={avatarUrl} onChange={(event) => setAvatarUrl(event.target.value)} placeholder="https://..." />
          </label>
          <button className="primary-button" type="submit">
            <Check size={15} /> {lang === "ar" ? "حفظ" : "Save"}
          </button>
        </form>
        <div className="panel signal-panel">
          <div className="panel-heading">
            <h2>{lang === "ar" ? "الأمان" : "Security"}</h2>
            <ShieldCheck size={18} />
          </div>
          <form onSubmit={changePassword}>
            <label>
              {lang === "ar" ? "كلمة المرور الحالية" : "Current password"}
              <input value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} type="password" required />
            </label>
            <label>
              {lang === "ar" ? "كلمة المرور الجديدة" : "New password"}
              <input value={newPassword} onChange={(event) => setNewPassword(event.target.value)} type="password" minLength={8} required />
            </label>
            <button className="secondary-button" type="submit">
              {lang === "ar" ? "تحديث كلمة المرور" : "Update password"}
            </button>
          </form>
          {profile.two_factor_eligible && (
            <div className="config-row" style={{ marginTop: 16 }}>
              <span>
                <strong>{lang === "ar" ? "التحقق الثنائي (2FA)" : "Two-factor authentication"}</strong>
                <small>{profile.totp_enabled ? (lang === "ar" ? "مفعّل" : "Enabled") : (lang === "ar" ? "غير مفعّل" : "Disabled")}</small>
              </span>
              {profile.totp_enabled ? (
                <button className="secondary-button" onClick={disableTwoFactor}>{lang === "ar" ? "إيقاف" : "Disable"}</button>
              ) : (
                <button className="secondary-button" onClick={startTwoFactorSetup}>{lang === "ar" ? "تفعيل" : "Enable"}</button>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="panel recent-panel">
        <div className="panel-heading">
          <h2>{lang === "ar" ? "آخر النشاطات" : "Recent activity"}</h2>
          <Activity size={18} />
        </div>
        <div className="config-list">
          {profile.recent_activity.length === 0 && (
            <div className="empty-state">{lang === "ar" ? "لا يوجد نشاط حديث." : "No recent activity."}</div>
          )}
          {profile.recent_activity.map((entry) => (
            <div className="config-row" key={entry.id}>
              <span>
                <strong>{entry.action}</strong>
                <small>{entry.entity_type}</small>
              </span>
              <small>{new Date(entry.created_at).toLocaleString(lang === "ar" ? "ar" : "en")}</small>
            </div>
          ))}
        </div>
      </div>
      {twoFactorModal && (
        <div className="modal-backdrop" onClick={() => setTwoFactorModal(false)}>
          <div className="source-modal" onClick={(event) => event.stopPropagation()}>
            <div className="modal-heading">
              <h2>{lang === "ar" ? "إعداد التحقق الثنائي" : "Set up 2FA"}</h2>
              <button type="button" className="icon-button" onClick={() => setTwoFactorModal(false)}>
                <X size={16} />
              </button>
            </div>
            <p>{lang === "ar" ? "امسح رمز QR باستخدام تطبيق المصادقة، ثم أدخل الرمز المكوّن من 6 أرقام." : "Scan the QR code with your authenticator app, then enter the 6-digit code."}</p>
            {qrCode && <img src={qrCode} alt="2FA QR code" style={{ width: 180, height: 180, margin: "12px auto", display: "block" }} />}
            <p className="subhead">{lang === "ar" ? "أو أدخل المفتاح يدويًا:" : "Or enter this key manually:"} <code>{secret}</code></p>
            <label>
              {lang === "ar" ? "رمز التحقق" : "Verification code"}
              <input value={twoFactorCode} onChange={(event) => setTwoFactorCode(event.target.value)} maxLength={6} inputMode="numeric" />
            </label>
            <button className="primary-button" onClick={confirmTwoFactor}>
              {lang === "ar" ? "تفعيل" : "Enable"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function QuickIngestModal({ token, lang, onClose }: { token: string; lang: Lang; onClose: () => void }) {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicId, setTopicId] = useState<number | null>(null);
  const [mode, setMode] = useState<"url" | "file">("url");
  const [url, setUrl] = useState("");
  const [backfill, setBackfill] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [caption, setCaption] = useState("");
  const [stage, setStage] = useState<"idle" | "working" | "done" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void get<Topic[]>("/api/v1/topics", token)
      .then((items) => {
        setTopics(items);
        setTopicId((current) => current ?? items[0]?.id ?? null);
      })
      .catch(() => setTopics([]));
  }, [token]);

  const runWithProgress = async (task: () => Promise<string>) => {
    setStage("working");
    setMessage(lang === "ar" ? "جارٍ التحليل..." : "Analyzing...");
    const progressTimer = window.setTimeout(
      () => setMessage(lang === "ar" ? "جارٍ تشغيل OCR/Whisper..." : "Running OCR/Whisper..."),
      900,
    );
    try {
      const summary = await task();
      setStage("done");
      setMessage(summary);
    } catch (cause) {
      setStage("error");
      setMessage(cause instanceof ApiError ? cause.message : (lang === "ar" ? "تعذر الإدراج." : "Ingestion failed."));
    } finally {
      window.clearTimeout(progressTimer);
    }
  };

  const submitUrl = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!topicId) return;
    await runWithProgress(async () => {
      const result = await request<{ saved: number; platform: string }>("/api/v1/ingestion/quick-url", token, {
        method: "POST",
        body: JSON.stringify({ topic_id: topicId, url, backfill }),
      });
      return lang === "ar"
        ? `تم إدراج ${result.saved} منشور (${result.platform}).`
        : `Ingested ${result.saved} post(s) from ${result.platform}.`;
    });
  };

  const submitFile = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!topicId || !file) return;
    await runWithProgress(async () => {
      const form = new FormData();
      form.append("topic_id", String(topicId));
      form.append("caption", caption);
      form.append("file", file);
      const result = await request<{ media_status: string }>("/api/v1/ingestion/quick-file", token, {
        method: "POST",
        body: form,
      });
      return lang === "ar" ? `تم الإدراج (${result.media_status}).` : `Ingested (${result.media_status}).`;
    });
  };

  const reset = () => {
    setUrl("");
    setFile(null);
    setCaption("");
    setStage("idle");
    setMessage("");
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="source-modal quick-ingest-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-heading">
          <h2>{lang === "ar" ? "إدراج سريع" : "Quick Ingest"}</h2>
          <button type="button" className="icon-button" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <p className="subhead">
          {lang === "ar"
            ? "الصق رابط منشور/قناة أو ارفع صورة/فيديو للمعالجة الفورية دون انتظار الموافقة."
            : "Paste a post/channel URL or upload an image/video for immediate processing, no approval needed."}
        </p>
        <label>
          {lang === "ar" ? "الموضوع" : "Topic"}
          <select value={topicId ?? ""} onChange={(event) => setTopicId(Number(event.target.value))}>
            {topics.map((topic) => (
              <option value={topic.id} key={topic.id}>{topic.title}</option>
            ))}
          </select>
        </label>
        <div className="config-tabs">
          <button type="button" className={mode === "url" ? "selected" : ""} onClick={() => { setMode("url"); reset(); }}>
            {lang === "ar" ? "رابط" : "URL"}
          </button>
          <button type="button" className={mode === "file" ? "selected" : ""} onClick={() => { setMode("file"); reset(); }}>
            {lang === "ar" ? "رفع ملف" : "Upload file"}
          </button>
        </div>
        {mode === "url" ? (
          <form key="url-form" onSubmit={submitUrl}>
            <label>
              {lang === "ar" ? "رابط المنشور/القناة" : "Post/channel URL"}
              <input value={url ?? ""} onChange={(event) => setUrl(event.target.value)} placeholder="https://..." required />
            </label>
            <label className="quick-ingest-checkbox">
              <input type="checkbox" checked={backfill ?? false} onChange={(event) => setBackfill(event.target.checked)} />
              {lang === "ar" ? "جلب المنشورات التاريخية (آخر 50 عنصر)" : "Fetch historical posts (backfill last 50 items)"}
            </label>
            <button className="primary-button" type="submit" disabled={stage === "working"}>
              {stage === "working" ? <span className="loading-spinner" /> : <Plus size={15} />}
              {lang === "ar" ? "إدراج" : "Ingest"}
            </button>
          </form>
        ) : (
          <form key="file-form" onSubmit={submitFile}>
            <label className="knowledge-file-field">
              {lang === "ar" ? "الملف (صورة أو فيديو)" : "File (image or video)"}
              <input type="file" accept="image/*,video/*,audio/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            </label>
            <label>
              {lang === "ar" ? "تعليق (اختياري)" : "Caption (optional)"}
              <input value={caption ?? ""} onChange={(event) => setCaption(event.target.value)} />
            </label>
            <button className="primary-button" type="submit" disabled={stage === "working" || !file}>
              {stage === "working" ? <span className="loading-spinner" /> : <Plus size={15} />}
              {lang === "ar" ? "إدراج" : "Ingest"}
            </button>
          </form>
        )}
        {message && (
          <div className={stage === "error" ? "data-error" : "connection-message"}>{message}</div>
        )}
      </div>
    </div>
  );
}

function Monitoring({ token, lang }: { token: string; lang: Lang }) {
  const [tab, setTab] = useState<"sources" | "keywords">("sources");
  const [items, setItems] = useState<Item[]>([]);
  const [page, setPage] = useState(1);
  const [editingItem, setEditingItem] = useState<Item | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState("");
  const [platform, setPlatform] = useState("rss");
  const [value, setValue] = useState("");
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicId, setTopicId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const platforms = [
    ["rss", "RSS"],
    ["telegram", lang === "ar" ? "تيليجرام" : "Telegram"],
    ["facebook", lang === "ar" ? "فيسبوك" : "Facebook"],
    ["instagram", lang === "ar" ? "إنستجرام" : "Instagram"],
    ["reddit", lang === "ar" ? "ريديت" : "Reddit"],
    ["youtube", lang === "ar" ? "يوتيوب" : "YouTube"],
    ["x", "X (Twitter)"],
    ["tiktok", "TikTok"],
    ["threads", "Threads"],
  ] as const;
  const pageSize = 5;
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const visibleItems = items.slice((page - 1) * pageSize, page * pageSize);
  const load = (selectedTopicId = topicId) => {
    if (!selectedTopicId) return;
    const path = `/api/v1/topics/${selectedTopicId}/${tab}`;
    void get<Item[]>(path, token)
      .then(setItems)
      .catch((cause) => {
        setItems([]);
        setError(
          cause instanceof ApiError ? cause.message : (lang === "ar" ? "تعذر تحميل البيانات." : "Unable to load data."),
        );
      });
  };
  useEffect(() => {
    void get<Topic[]>("/api/v1/topics", token)
      .then((nextTopics) => {
        setTopics(nextTopics);
        setTopicId((current) => current ?? nextTopics[0]?.id ?? null);
      })
      .catch((cause) =>
        setError(
          cause instanceof ApiError ? cause.message : (lang === "ar" ? "تعذر تحميل المواضيع." : "Unable to load topics."),
        ),
      );
  }, [token]);
  useEffect(() => {
    load();
  }, [tab, token, topicId]);
  const openCreate = () => {
    setEditingItem(null);
    setName("");
    setPlatform("rss");
    setValue("");
    setError("");
    setNotice("");
    setFormOpen(true);
  };
  const openEdit = (item: Item) => {
    setEditingItem(item);
    setName(item.name ?? "");
    setPlatform(item.platform ?? "rss");
    setValue(item.url_or_handle ?? item.word_or_phrase ?? "");
    setError("");
    setNotice("");
    setFormOpen(true);
  };
  const remove = async (item: Item) => {
    if (!topicId || !window.confirm(lang === "ar" ? "هل تريد حذف هذا السجل؟" : "Delete this record?")) return;
    try {
      await request<void>(
        `/api/v1/topics/${topicId}/${tab}/${item.id}`,
        token,
        { method: "DELETE" },
      );
      if (visibleItems.length === 1 && page > 1) setPage(page - 1);
      load();
      setNotice(lang === "ar" ? "تم حذف السجل." : "Record deleted.");
    } catch (cause) {
      setNotice("");
      setError(cause instanceof ApiError && cause.status === 409 ? (lang === "ar" ? "الرابط أو الحساب مضاف بالفعل." : "This URL or handle already exists.") : cause instanceof ApiError ? cause.message : (lang === "ar" ? "تعذر حذف السجل." : "Unable to delete the record."));
    }
  };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!topicId) return;
    const body =
      tab === "sources"
        ? {
            name,
            platform,
            url_or_handle: value,
            target_type: "url",
            is_active: true,
          }
        : { word_or_phrase: value, category: "general", is_active: true };
    try {
      await request<Item>(
        editingItem
          ? `/api/v1/topics/${topicId}/${tab}/${editingItem.id}`
          : `/api/v1/topics/${topicId}/${tab}`,
        token,
        { method: editingItem ? "PUT" : "POST", body: JSON.stringify(body) },
      );
      setName("");
      setPlatform("rss");
      setValue("");
      setEditingItem(null);
      setFormOpen(false);
      load();
      setNotice(editingItem ? (lang === "ar" ? "تم تحديث السجل بنجاح." : "Record updated successfully.") : (lang === "ar" ? "تم حفظ الرابط بنجاح." : "Source saved successfully."));
    } catch (cause) {
      setNotice("");
      setError(cause instanceof ApiError && cause.status === 409 ? (lang === "ar" ? "الرابط أو الحساب مضاف بالفعل، ولم يتم حفظه مرة أخرى." : "This URL or handle already exists and was not saved again.") : cause instanceof ApiError ? cause.message : (lang === "ar" ? "تعذر حفظ السجل." : "Unable to save the record."));
    }
  };
  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">{lang === "ar" ? "إعدادات المراقبة" : "Monitoring settings"}</p>
          <h1>{lang === "ar" ? "إدارة الروابط والكلمات المفتاحية" : "Manage sources & keywords"}</h1>
          <p className="subhead">{lang === "ar" ? "إدارة العناصر التي تستخدمها عملية الجمع." : "Manage the items used by the collection process."}</p>
        </div>
        <button className="primary-button" onClick={openCreate}>
          <Plus size={16} /> {lang === "ar" ? "إضافة جديدة" : "Add new"}
        </button>
      </div>
      {error && <div className="data-error">{error}</div>}
      {notice && <div className="connection-message">{notice}</div>}
      <div className="config-tabs">
        <select
          value={topicId ?? ""}
          onChange={(event) => setTopicId(Number(event.target.value))}
          disabled={!topics.length}
        >
          {topics.map((topic) => (
            <option value={topic.id} key={topic.id}>
              {topic.title}
            </option>
          ))}
        </select>
        <button
          className={tab === "sources" ? "selected" : ""}
          onClick={() => setTab("sources")}
        >
          {lang === "ar" ? "الروابط والمصادر" : "Sources"} ({tab === "sources" ? items.length : "..."})
        </button>
        <button
          className={tab === "keywords" ? "selected" : ""}
          onClick={() => setTab("keywords")}
        >
          {lang === "ar" ? "الكلمات المفتاحية" : "Keywords"} ({tab === "keywords" ? items.length : "..."})
        </button>
      </div>
      <div className="panel config-list">
        {visibleItems.map((item) => (
          <div className="config-row" key={item.id}>
            <span className="config-icon">
              {tab === "sources" ? item.platform?.[0].toUpperCase() : "#"}
            </span>
            <span>
              <strong>
                {tab === "sources" ? item.name : item.word_or_phrase}
              </strong>
              <small>
                {tab === "sources" ? item.url_or_handle : item.category}
              </small>
            </span>
            <span className="badge badge-neutral">
              {item.status ?? (item.is_active ? (lang === "ar" ? "نشط" : "Active") : (lang === "ar" ? "متوقف" : "Disabled"))}
            </span>
            <span className="config-actions">
              <button
                className="icon-button"
                title={lang === "ar" ? "تعديل" : "Edit"}
                aria-label={lang === "ar" ? "تعديل" : "Edit"}
                onClick={() => openEdit(item)}
              >
                <Edit3 size={15} />
              </button>
              <button
                className="icon-button danger-button"
                title={lang === "ar" ? "حذف" : "Delete"}
                aria-label={lang === "ar" ? "حذف" : "Delete"}
                onClick={() => remove(item)}
              >
                <Trash2 size={15} />
              </button>
            </span>
          </div>
        ))}
        {!items.length && (
          <div className="empty-state">{lang === "ar" ? "لا توجد عناصر مضافة بعد." : "No items added yet."}</div>
        )}
      </div>
      {items.length > 0 && (
        <div className="pagination">
          <button
            className="secondary-button"
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
          >
            {lang === "ar" ? "السابق" : "Previous"}
          </button>
          <span>
            {lang === "ar" ? `صفحة ${page} من ${pageCount}` : `Page ${page} of ${pageCount}`}
          </span>
          <button
            className="secondary-button"
            disabled={page === pageCount}
            onClick={() => setPage(page + 1)}
          >
            {lang === "ar" ? "التالي" : "Next"}
          </button>
        </div>
      )}
      {formOpen && (
        <div className="modal-backdrop" onClick={() => setFormOpen(false)}>
          <form
            className="source-modal"
            onSubmit={submit}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-heading">
              <h2>
                {editingItem
                  ? (lang === "ar" ? "تعديل السجل" : "Edit record")
                  : tab === "sources"
                    ? (lang === "ar" ? "إضافة رابط مصدر" : "Add source URL")
                    : (lang === "ar" ? "إضافة كلمة مفتاحية" : "Add keyword")}
              </h2>
              <button
                type="button"
                className="icon-button"
                onClick={() => setFormOpen(false)}
              >
                <X size={18} />
              </button>
            </div>
            {tab === "sources" && (
              <>
                <label>
                  {lang === "ar" ? "اسم المصدر" : "Source name"}
                  <input
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    required
                  />
                </label>
                <label>
                  {lang === "ar" ? "المنصة" : "Platform"}
                  <select
                    value={platform}
                    onChange={(event) => setPlatform(event.target.value)}
                  >
                    {platforms.map(([option, label]) => (
                      <option value={option} key={option}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
            <label>
              {tab === "sources" ? (lang === "ar" ? "الرابط أو الحساب" : "URL or handle") : (lang === "ar" ? "الكلمة أو العبارة" : "Keyword or phrase")}
              <input
                value={value}
                onChange={(event) => setValue(event.target.value)}
                required
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setFormOpen(false)}
              >
                {lang === "ar" ? "إلغاء" : "Cancel"}
              </button>
              <button type="submit" className="primary-button">
                <Check size={15} /> {lang === "ar" ? "حفظ" : "Save"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
function PromptSettingsPanel({ token, role, lang, section = "connection" }: { token: string; role: Role; lang: Lang; section?: "connection" | "prompts" }) {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [selectedTopicId, setSelectedTopicId] = useState<number | null>(null);
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [templateText, setTemplateText] = useState(() =>
    lang === "ar"
      ? "حلل المحتوى المرصود حول الموضوع المحدد، وحدد أهم الادعاءات والمخاطر ومستوى الأولوية، ثم قدم ملخصاً واضحاً باللغة العربية."
      : "Analyze the monitored content for the selected topic, identify the key claims, risks, and priority level, then provide a clear summary.",
  );
  const [name, setName] = useState(() => (lang === "ar" ? "تحليل المحتوى" : "Content analysis"));
  const [provider, setProvider] = useState("ollama");
  const [modelName, setModelName] = useState(AI_PROVIDER_DEFAULTS.ollama.model);
  const [availableModels, setAvailableModels] = useState<string[]>(AI_PROVIDER_DEFAULTS.ollama.models);
  const [baseUrl, setBaseUrl] = useState(AI_PROVIDER_DEFAULTS.ollama.baseUrl);
  const [apiKey, setApiKey] = useState("");
  const [hasApiKey, setHasApiKey] = useState(false);
  const [configured, setConfigured] = useState(false);
  const [connectionMessage, setConnectionMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<string>("");
  const [testResult, setTestResult] = useState<{ renderedPrompt: string; analysis: Record<string, unknown> } | null>(null);

  const providerOptions = [
    { value: "ollama", label: "Ollama" },
    { value: "openrouter", label: "OpenRouter" },
    { value: "google_ai_studio", label: "Google AI Studio" },
    { value: "custom_openai", label: lang === "ar" ? "مزود OpenAI-compatible" : "OpenAI-compatible" },
  ];

  const providerHelp = AI_PROVIDER_DEFAULTS[provider]?.baseUrl ?? AI_PROVIDER_DEFAULTS.ollama.baseUrl;

  const applyProviderDefaults = (nextProvider: string) => {
    const defaults = AI_PROVIDER_DEFAULTS[nextProvider] ?? AI_PROVIDER_DEFAULTS.ollama;
    setProvider(nextProvider);
    setModelName(defaults.model);
    setAvailableModels(defaults.models);
    setBaseUrl(defaults.baseUrl);
    setConnectionMessage("");
  };

  const connectionPayload = () => ({
    provider,
    model: modelName,
    base_url: baseUrl.trim() || providerHelp,
    api_key: apiKey || null,
  });

  useEffect(() => {
    get<AiStatus>("/api/ai/status", token)
      .then((status) => {
        if (status.provider && status.provider !== "disabled") setProvider(status.provider);
        if (status.model) setModelName(status.model);
        if (status.available_models?.length) setAvailableModels(status.available_models);
      })
      .catch(() => undefined);
  }, [token]);

  useEffect(() => {
    get<{ provider: string; model: string; base_url: string; has_api_key: boolean; configured: boolean }>("/api/ai/config", token)
      .then((config) => {
        setProvider(config.provider);
        setModelName(config.model);
        setBaseUrl(config.base_url);
        setHasApiKey(config.has_api_key);
        setConfigured(config.configured);
      })
      .catch(() => undefined);
  }, [token]);

  useEffect(() => {
    if (section !== "prompts") return;
    get<{ provider: string; models: string[] }>("/api/ai/config/models", token)
      .then((response) => {
        if (response.provider) setProvider(response.provider);
        if (response.models.length) {
          setAvailableModels(response.models);
          setModelName((current) => response.models.includes(current) ? current : response.models[0]);
        }
      })
      .catch(() => undefined);
  }, [section, token]);

  useEffect(() => {
    get<Topic[]>("/api/v1/topics", token)
      .then((nextTopics) => {
        setTopics(nextTopics);
        if (!selectedTopicId && nextTopics[0]) setSelectedTopicId(nextTopics[0].id);
      })
      .catch(() => setTopics([]));
  }, [token]);

  useEffect(() => {
    if (!selectedTopicId) return;
    get<PromptTemplate[]>(`/api/ai/topics/${selectedTopicId}/prompts`, token)
      .then(setTemplates)
      .catch(() => setTemplates([]));
  }, [selectedTopicId, token]);

  const canManage = role === "super_admin" || role === "topic_manager";
  if (!canManage) return null;

  const testPrompt = async () => {
    if (!selectedTopicId) return;
    setTesting(true);
    setTestResult(null);
    setResult("");
    try {
      const response = await request<{ rendered_prompt: string; analysis: Record<string, unknown> }>(`/api/ai/topics/${selectedTopicId}/prompts/test`, token, {
        method: "POST",
        body: JSON.stringify({
          topic_id: selectedTopicId,
          name,
          template: templateText,
          variables: "topic_name,posts_content,keywords,time_range",
          provider,
          model_name: modelName,
          is_active: true,
        }),
      });
      setTestResult({ renderedPrompt: response.rendered_prompt, analysis: response.analysis });
      setResult("");
    } catch (error) {
      setTestResult(null);
      setResult(error instanceof Error ? error.message : (lang === "ar" ? "تعذر اختبار النموذج." : "Prompt test failed."));
    } finally {
      setTesting(false);
    }
  };

  const savePrompt = async () => {
    if (!selectedTopicId) return;
    setSaving(true);
    try {
      await request(`/api/ai/topics/${selectedTopicId}/prompts`, token, {
        method: "POST",
        body: JSON.stringify({
          topic_id: selectedTopicId,
          name,
          template: templateText,
          variables: "topic_name,posts_content,keywords,time_range",
          provider,
          model_name: modelName,
          is_active: true,
        }),
      });
      setResult(lang === "ar" ? "تم حفظ النموذج بنجاح." : "Prompt saved successfully.");
    } catch {
      setResult(lang === "ar" ? "تعذر حفظ النموذج." : "Unable to save prompt.");
    } finally {
      setSaving(false);
    }
  };

  const saveConnection = async () => {
    try {
      const payload = connectionPayload();
      const config = await request<{ has_api_key: boolean }>("/api/ai/config", token, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setHasApiKey(config.has_api_key);
      setConfigured(true);
      setBaseUrl(payload.base_url);
      setApiKey("");
      setConnectionMessage(lang === "ar" ? "تم حفظ إعدادات الاتصال." : "Connection settings saved.");
    } catch (error) {
      const detail = error instanceof Error ? error.message : "";
      setConnectionMessage(lang === "ar" ? `تعذر حفظ إعدادات الاتصال. ${detail}` : `Unable to save connection settings. ${detail}`);
    }
  };

  const testConnection = async () => {
    try {
      const payload = connectionPayload();
      await request("/api/ai/config", token, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      const response = await request<{ models: string[] }>("/api/ai/config/test", token, { method: "POST" });
      setBaseUrl(payload.base_url);
      setAvailableModels(response.models);
      if (response.models.length && !response.models.includes(modelName)) setModelName(response.models[0]);
      setConnectionMessage(`${lang === "ar" ? "تم الاتصال بنجاح. النماذج المتاحة: " : "Connected. Available models: "}${response.models.length}`);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "";
      setConnectionMessage(lang === "ar" ? `فشل الاتصال. تحقق من الرابط والتوكن. ${detail}` : `Connection failed. Check the URL and token. ${detail}`);
    }
  };

  const fetchModels = async () => {
    try {
      const payload = connectionPayload();
      await request("/api/ai/config", token, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      const response = await request<{ models: string[] }>("/api/ai/config/models", token);
      setBaseUrl(payload.base_url);
      setAvailableModels(response.models);
      setConnectionMessage(lang === "ar" ? `تم جلب ${response.models.length} نموذجاً.` : `Fetched ${response.models.length} models.`);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "";
      setConnectionMessage(lang === "ar" ? `تعذر جلب النماذج. ${detail}` : `Unable to fetch models. ${detail}`);
    }
  };

  return (
    <div className="ai-settings-workspace">
      {section === "connection" ? (
        <div className="panel ai-settings-card">
          <div className="ai-card-heading">
            <div>
              <p className="eyebrow">PROVIDER</p>
              <h2>{lang === "ar" ? "اتصال مزود الذكاء الاصطناعي" : "AI provider connection"}</h2>
              <p>{lang === "ar" ? "أدخل بيانات الاتصال لجلب النماذج الحقيقية من المزود." : "Enter connection details to discover live models from your provider."}</p>
            </div>
            <span className={`connection-status ${configured ? "ready" : "missing"}`}>
              <span />{configured ? (lang === "ar" ? "جاهز للاتصال" : "Ready to connect") : (lang === "ar" ? "يحتاج إعداداً" : "Needs setup")}
            </span>
          </div>
          <div className="ai-connection-layout">
          <div className="config-list connection-form">
            <div className="provider-grid">
              <label>
                {lang === "ar" ? "مزود الذكاء الاصطناعي" : "AI provider"}
                <select value={provider} onChange={(event) => {
                  applyProviderDefaults(event.target.value);
                }}>
                  {providerOptions.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label>
                {lang === "ar" ? "الموديل الافتراضي" : "Default model"}
                <select value={modelName} onChange={(event) => setModelName(event.target.value)}>
                  {availableModels.map((option) => <option value={option} key={option}>{option}</option>)}
                </select>
              </label>
            </div>
            <label>
              {lang === "ar" ? "رابط الخدمة" : "Service URL"}
              <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://..." />
              <small className="field-help">{lang === "ar" ? `مثال: ${providerHelp}` : `Example: ${providerHelp}`}</small>
            </label>
            <label>
              {lang === "ar" ? "مفتاح API" : "API key"}
              <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={hasApiKey ? (lang === "ar" ? "مفتاح محفوظ، اتركه فارغاً للإبقاء عليه" : "Key saved, leave blank to keep it") : (lang === "ar" ? "أدخل مفتاح API" : "Enter API key")} />
            </label>
            <div className="config-actions connection-actions">
              <button type="button" className="secondary-button" onClick={fetchModels}><Database size={15} />{lang === "ar" ? "جلب النماذج" : "Fetch models"}</button>
              <button type="button" className="secondary-button" onClick={testConnection}><Activity size={15} />{lang === "ar" ? "اختبار الاتصال" : "Test connection"}</button>
              <button type="button" className="primary-button" onClick={saveConnection}><Check size={15} />{lang === "ar" ? "حفظ الإعدادات" : "Save settings"}</button>
            </div>
            {connectionMessage && <div className="connection-message">{connectionMessage}</div>}
          </div>
          <div className="model-card-grid">
            <div className="model-info-card"><span className="model-card-label">{lang === "ar" ? "المزود النشط" : "Active provider"}</span><strong>{providerOptions.find((option) => option.value === provider)?.label ?? provider}</strong><small>{baseUrl}</small></div>
            <div className="model-info-card"><span className="model-card-label">{lang === "ar" ? "الموديل المحدد" : "Selected model"}</span><strong>{modelName || "-"}</strong><small>{lang === "ar" ? "سيستخدمه المحرك للتحليل" : "Used by the analysis engine"}</small></div>
            <div className="model-info-card"><span className="model-card-label">{lang === "ar" ? "حالة الاعتماد" : "Credential status"}</span><strong>{configured ? (lang === "ar" ? "جاهز" : "Ready") : (lang === "ar" ? "غير مكتمل" : "Incomplete")}</strong><small>{["ollama", "custom_openai"].includes(provider) ? (lang === "ar" ? "مفتاح API اختياري" : "API key optional") : hasApiKey ? (lang === "ar" ? "مفتاح محفوظ" : "API key saved") : (lang === "ar" ? "أدخل المفتاح" : "Enter an API key")}</small></div>
            <div className="model-info-card"><span className="model-card-label">{lang === "ar" ? "النماذج المتاحة" : "Available models"}</span><strong>{availableModels.length}</strong><small>{lang === "ar" ? "من آخر اتصال ناجح" : "From the latest successful connection"}</small></div>
          </div>
          </div>
        </div>
      ) : (
      <div className="panel ai-settings-card">
        <div className="ai-card-heading">
          <div>
            <p className="eyebrow">ANALYSIS</p>
            <h2>{lang === "ar" ? "تعليمات التحليل" : "Analysis instructions"}</h2>
            <p>{lang === "ar" ? "أنشئ تعليمات مخصصة لكل موضوع واختبرها قبل الحفظ." : "Create topic-specific instructions and test them before saving."}</p>
          </div>
          <span className="template-count">{templates.length} {lang === "ar" ? "قوالب" : "templates"}</span>
        </div>
        <div className="config-list prompt-composer-shell">
          <label>
            {lang === "ar" ? "الموضوع" : "Topic"}
            <select value={selectedTopicId ?? ""} onChange={(event) => setSelectedTopicId(Number(event.target.value))}>
              {topics.map((topic) => <option value={topic.id} key={topic.id}>{topic.title}</option>)}
            </select>
          </label>

          <div className="prompt-composer">
          <div className="prompt-composer-header">
            <span className="prompt-pill">{lang === "ar" ? "الموديل" : "Model"}</span>
            <div className="prompt-selects">
              <select value={provider} onChange={(event) => setProvider(event.target.value)}>
                {providerOptions.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
              </select>
              <select value={modelName} onChange={(event) => setModelName(event.target.value)}>
                {availableModels.map((option) => <option value={option} key={option}>{option}</option>)}
              </select>
            </div>
          </div>

          <label className="prompt-name-label">
            {lang === "ar" ? "عنوان البرومبت" : "Prompt title"}
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>

          <div className="chatgpt-editor">
            <div className="chatgpt-editor-toolbar">
              <span>{lang === "ar" ? "تعليمات التحليل" : "Analysis instructions"}</span>
              <span className="chatgpt-chip">{providerOptions.find((option) => option.value === provider)?.label ?? provider}</span>
            </div>
            <textarea value={templateText} onChange={(event) => setTemplateText(event.target.value)} rows={10} placeholder={lang === "ar" ? "اكتب تعليمات التحليل هنا..." : "Write analysis instructions here..."} />
          </div>

          <div className="config-actions composer-actions">
            <button type="button" className="secondary-button" onClick={testPrompt} disabled={testing} aria-busy={testing}>
              {testing ? <span className="loading-spinner" aria-hidden="true" /> : <Eye size={15} />}
              {testing ? (lang === "ar" ? "النموذج يعمل، انتظر النتائج..." : "Model is working, waiting for results...") : (lang === "ar" ? "معاينة واختبار" : "Preview & test")}
            </button>
            <button type="button" className="primary-button" disabled={saving} onClick={savePrompt}><Check size={15} />{lang === "ar" ? "حفظ البرومبت" : "Save prompt"}</button>
          </div>
        </div>
        {testing && <div className="prompt-test-waiting" role="status"><span className="loading-spinner" aria-hidden="true" /><div><strong>{lang === "ar" ? "جارٍ تشغيل النموذج" : "Running the model"}</strong><small>{lang === "ar" ? "قد يستغرق التحليل وقتًا أطول حسب سرعة الجهاز وحجم النموذج." : "Analysis may take longer depending on your device speed and model size."}</small></div></div>}
        {result && <div className="data-error" style={{ whiteSpace: "pre-wrap" }}>{result}</div>}
        {testResult && <div className="prompt-test-result">
          <div className="test-result-heading"><div><span className="result-success-dot" /><strong>{lang === "ar" ? "نتيجة الاختبار" : "Test result"}</strong></div><span className="chatgpt-chip">{providerOptions.find((option) => option.value === provider)?.label ?? provider} · {modelName}</span></div>
          <div className="test-result-grid">
            <div className="test-result-summary"><span>{lang === "ar" ? "ملخص التحليل" : "Analysis summary"}</span><p>{String(testResult.analysis.ai_summary ?? (lang === "ar" ? "لم يتم إرجاع ملخص." : "No summary returned."))}</p></div>
            <div className="test-result-meta"><span>{lang === "ar" ? "مستوى الخطورة" : "Severity"}</span><strong>{String(testResult.analysis.severity_level ?? "-")}</strong></div>
            <div className="test-result-meta"><span>{lang === "ar" ? "التصنيف" : "Category"}</span><strong>{String(testResult.analysis.violence_category ?? (lang === "ar" ? "لا يوجد" : "None"))}</strong></div>
            <div className="test-result-meta"><span>{lang === "ar" ? "للمراجعة" : "Flagged"}</span><strong>{testResult.analysis.is_flagged ? (lang === "ar" ? "نعم" : "Yes") : (lang === "ar" ? "لا" : "No")}</strong></div>
          </div>
          <details className="rendered-prompt-details"><summary>{lang === "ar" ? "عرض النص المرسل للمحرك" : "Show rendered prompt"}</summary><p>{testResult.renderedPrompt}</p></details>
        </div>}
        </div>
      </div>
      )}
    </div>
  );
}

export default function Home() {
  const [lang, setLang] = useState<Lang>("ar");
  const [token, setToken] = useState("");
  const [role, setRole] = useState<Role>("observer");
  const [page, setPage] = useState<Page>("overview");
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setToken(window.localStorage.getItem("signaldesk_token") ?? "");
      setRole(
        (window.localStorage.getItem("signaldesk_role") as Role) ??
          "topic_monitor",
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => {
    void fetch(`${API}/api/setup/status`, { cache: "no-store" })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((data: { needs_setup: boolean }) => setSetupRequired(data.needs_setup))
      .catch(() => setSetupRequired(false));
  }, []);
  useEffect(() => {
    // request() clears localStorage and fires this on a 401; sync React state so polling stops.
    const onExpired = () => setToken("");
    window.addEventListener("signaldesk-auth-expired", onExpired);
    return () => window.removeEventListener("signaldesk-auth-expired", onExpired);
  }, []);
  const onLogin = (nextToken: string, nextRole: Role) => {
    const normalized = ["admin", "topic_admin", "topic_monitor"].includes(nextRole) ? (nextRole === "admin" ? "super_admin" : nextRole === "topic_admin" ? "topic_manager" : "analyst") : nextRole;
    window.localStorage.setItem("signaldesk_token", nextToken);
    window.localStorage.setItem("signaldesk_role", normalized);
    setToken(nextToken);
    setRole(normalized as Role);
  };
  const toggle = () => {
    const next = lang === "ar" ? "en" : "ar";
    setLang(next);
    setApiLang(next);
    document.documentElement.lang = next;
    document.documentElement.dir = next === "ar" ? "rtl" : "ltr";
  };
  const signOut = () => {
    window.localStorage.removeItem("signaldesk_token");
    window.localStorage.removeItem("signaldesk_role");
    setToken("");
  };
  const adminRequest = <T,>(path: string, init?: RequestInit) =>
    request<T>(path, token, init);
  const isRestricted = role === "observer" || role === "analyst" || role === "topic_monitor";
  const isManager = role === "topic_manager" || role === "topic_admin" || role === "super_admin";
  const [pendingCount, setPendingCount] = useState(0);
  const [quickIngestOpen, setQuickIngestOpen] = useState(false);
  const [spiderStatus, setSpiderStatus] = useState<SpiderActiveStatus | null>(null);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);
  const [updateDismissed, setUpdateDismissed] = useState(false);
  useEffect(() => {
    if (!isManager || !token) return;
    void get<ApprovalsSummary>("/api/v1/topics/1/approvals", token)
      .then((data) => setPendingCount(data.sources.length + data.keywords.length))
      .catch(() => setPendingCount(0));
  }, [token, isManager, page]);
  useEffect(() => {
    if (!token) return;
    const load = () =>
      get<SpiderActiveStatus>("/api/v1/spider/active-status", token)
        .then(setSpiderStatus)
        .catch(() => setSpiderStatus(null));
    void load();
    const timer = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(timer);
  }, [token]);
  useEffect(() => {
    if (!token) return;
    const loadUpdateStatus = () => {
      void fetch(`${API}/api/system/update-status`, { cache: "no-store" })
        .then((response) => response.ok ? response.json() : Promise.reject())
        .then((data: UpdateStatus) => setUpdateStatus(data))
        .catch(() => setUpdateStatus(null));
    };
    loadUpdateStatus();
    const timer = window.setInterval(loadUpdateStatus, 900000);
    return () => window.clearInterval(timer);
  }, [token]);
  if (setupRequired === null) return <main className="setup-loading" aria-live="polite">Loading SignalDesk...</main>;
  if (setupRequired) return <SetupWizard lang={lang} toggleLanguage={toggle} onInitialized={onLogin} />;
  if (!token) return <Login lang={lang} onLogin={onLogin} toggle={toggle} />;
  const t = labels[lang];
  const allowedNavIds: readonly string[] = isRestricted
    ? ["overview", "feed"]
    : ["overview", "feed", "graph", "automation", "spider", "knowledge", "management", "audit", "prompts"];
  const navigationWithAdmin = [
    ...navigation[lang].filter(([id]) => allowedNavIds.includes(id)),
    ...(isRestricted ? ([["proposals", t.proposals, Plus]] as const) : []),
    ...(isManager ? ([["approvals", t.approvals, ShieldCheck]] as const) : []),
    ...(role === "super_admin"
      ? ([
          ["topics", lang === "ar" ? "إدارة المواضيع" : "Topic management", Database],
          ["users", lang === "ar" ? "إدارة المستخدمين" : "User management", Users],
        ] as const)
      : role === "topic_admin" || role === "topic_manager"
        ? ([["topics", lang === "ar" ? "إدارة المواضيع" : "Topic management", Database]] as const)
        : []),
  ];
  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <span />
          </span>
          <strong>
            signal<span>desk</span>
          </strong>
        </div>
        <nav>
          {navigationWithAdmin.map(([id, label, Icon]) => (
            <button
              className={`nav-item ${page === id ? "active" : ""}`}
              key={id}
              onClick={() => setPage(id as Page)}
            >
              <Icon size={18} />
              <span>{label}</span>
              {id === "approvals" && pendingCount > 0 && (
                <em className="nav-count">{pendingCount}</em>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button className="nav-item" onClick={() => setQuickIngestOpen(true)}>
            <Plus size={18} />
            <span>{lang === "ar" ? "إدراج سريع" : "Quick Ingest"}</span>
          </button>
          <button className="nav-item">
            <Settings2 size={18} />
            <span>{lang === "ar" ? "إعدادات مساحة العمل" : "Workspace settings"}</span>
          </button>
          <button className="nav-item" onClick={signOut}>
            <LogOut size={18} />
            <span>{t.signout}</span>
          </button>
        </div>
      </aside>
      <section className="main-area">
        <header className="topbar">
          <div className="crumbs">
            {t[page] ??
              (page === "topics"
                ? (lang === "ar" ? "إدارة المواضيع" : "Topic management")
                : (lang === "ar" ? "إدارة المستخدمين" : "User management"))}
          </div>
          <div className="topbar-actions">
            <label className="global-search">
              <Search size={17} />
              <input placeholder={lang === "ar" ? "بحث" : "Search"} />
            </label>
            <div className={`spider-status-badge ${spiderStatus?.is_running ? "running" : "idle"}`} title={lang === "ar" ? "حالة السبايدر" : "Spider status"}>
              <SpiderIcon size={17} />
              <span>
                {spiderStatus?.is_running
                  ? (lang === "ar" ? "السبايدر يعمل" : "Spider running")
                  : (lang === "ar" ? "السبايدر متوقف" : "Spider idle")}
              </span>
            </div>
            <button className="secondary-button" onClick={() => setQuickIngestOpen(true)}>
              <Plus size={15} /> {lang === "ar" ? "إدراج سريع" : "Quick Ingest"}
            </button>
            <button className="language-button" onClick={toggle}>
              {lang === "ar" ? "English" : "العربية"}
            </button>
            <button className="top-avatar" style={{ border: 0 }} onClick={() => setPage("profile")} title={t.profile}>AM</button>
          </div>
        </header>
        {updateStatus?.update_available && !updateDismissed && (
          <div className="update-banner" role="status">
            <div>
              <strong>{lang === "ar" ? "يتوفر تحديث جديد لـ SignalDesk" : "A new SignalDesk update is available"}</strong>
              <span>
                {lang === "ar" ? "الإصدار الحالي" : "Current"} {updateStatus.current_version.slice(0, 7)}
                {"  |  "}
                {lang === "ar" ? "الجديد" : "Latest"} {updateStatus.latest_version?.slice(0, 7)}
              </span>
            </div>
            <div className="update-banner-actions">
              {updateStatus.release_url && (
                <a href={updateStatus.release_url} target="_blank" rel="noreferrer" className="update-link">
                  <ExternalLink size={15} />
                  {lang === "ar" ? "عرض التحديث" : "View update"}
                </a>
              )}
              <button type="button" className="icon-button" onClick={() => setUpdateDismissed(true)} aria-label={lang === "ar" ? "إغلاق إشعار التحديث" : "Dismiss update notification"}>
                <X size={17} />
              </button>
            </div>
          </div>
        )}
        {page === "overview" ? (
          role === "super_admin" || role === "topic_manager" ? (
            <div className="dashboard-overview-layout">
              <div className="dashboard-prompt-column">
                <PromptSettingsPanel token={token} role={role} lang={lang} section="prompts" />
              </div>
              <div className="dashboard-data-column">
                <Dashboard token={token} lang={lang} />
              </div>
            </div>
          ) : (
            <Dashboard token={token} lang={lang} />
          )
        ) : page === "feed" ? (
          <Feed token={token} lang={lang} />
        ) : page === "graph" ? (
          <GraphPage token={token} request={adminRequest} lang={lang} />
        ) : page === "management" ? (
          <Monitoring token={token} lang={lang} />
        ) : page === "automation" ? (
          <AutomationMonitor token={token} role={role} lang={lang} />
        ) : page === "spider" ? (
          <SpiderMonitor token={token} lang={lang} />
        ) : page === "knowledge" ? (
          <KnowledgeBase token={token} lang={lang} />
        ) : page === "topics" ? (
          <TopicManagement request={adminRequest} role={role} lang={lang} />
        ) : page === "users" ? (
          <UserManagement request={adminRequest} role={role} lang={lang} />
        ) : page === "audit" ? (
          <AuditDashboard request={adminRequest} role={role} lang={lang} />
        ) : page === "approvals" && isManager ? (
          <ApprovalsPanel token={token} lang={lang} />
        ) : page === "proposals" && isRestricted ? (
          <ProposalsPanel token={token} lang={lang} />
        ) : page === "profile" ? (
          <ProfilePage token={token} lang={lang} />
        ) : page === "prompts" && (role === "super_admin" || role === "topic_manager") ? (
          <div className="page-content prompt-settings-page">
            <PromptSettingsPanel token={token} role={role} lang={lang} section="connection" />
          </div>
        ) : (
          <div className="page-content">
            <div className="panel placeholder-page">
              <h2>{t[page]}</h2>
              <p>
                {lang === "ar"
                  ? "هذه الصفحة قيد الإعداد."
                  : "This page is under construction."}
              </p>
            </div>
          </div>
        )}
      </section>
      {quickIngestOpen && (
        <QuickIngestModal token={token} lang={lang} onClose={() => setQuickIngestOpen(false)} />
      )}
    </main>
  );
}
const navigation = {
  ar: [
    ["overview", "نظرة عامة", LayoutDashboard],
    ["feed", "موجز الاستخبارات", Radio],
    ["graph", "شبكة الانتشار و CIB", Share2],
    ["automation", "مراقبة الأتمتة", Activity],
    ["spider", "متابعة السبايدر", SpiderIcon],
    ["knowledge", "قاعدة المعرفة", Database],
    ["management", "الروابط والكلمات المفتاحية", UserCog],
    ["audit", "سجلات التدقيق", ShieldCheck],
    ["prompts", "إعدادات الذكاء الاصطناعي", Settings2],
  ] as const,
  en: [
    ["overview", "Overview", LayoutDashboard],
    ["feed", "Intelligence feed", Radio],
    ["graph", "Propagation & CIB", Share2],
    ["automation", "Automation monitor", Activity],
    ["spider", "Spider monitor", SpiderIcon],
    ["knowledge", "Knowledge base", Database],
    ["management", "Sources & keywords", UserCog],
    ["audit", "Audit logs", ShieldCheck],
    ["prompts", "AI settings", Settings2],
  ] as const,
};
const strings = {
  ar: { signout: "تسجيل الخروج" },
  en: { signout: "Sign out" },
};
