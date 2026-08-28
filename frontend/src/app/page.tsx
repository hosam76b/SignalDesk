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
  Edit3,
  Eye,
  EyeOff,
  FileText,
  Globe2,
  LayoutDashboard,
  LogOut,
  Menu,
  PanelLeftClose,
  Plus,
  Radio,
  Search,
  Settings2,
  Share2,
  ShieldCheck,
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

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
type Lang = "ar" | "en";
type Page =
  | "overview"
  | "feed"
  | "graph"
  | "management"
  | "topics"
  | "members"
  | "users"
  | "automation"
  | "knowledge"
  | "audit"
  | "prompts";
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
};
type ScraperStatus = { status: "idle" | "running"; message: string; last_run?: string | null; is_running: boolean };
type ScrapingResult = { success: boolean; total_sources: number; total_posts_found: number; new_posts_saved: number; errors: { source?: string; error?: string }[]; duration_seconds: number; sources_processed: Record<string, { sources?: number; posts_found?: number; posts_saved?: number }> };
const labels = {
  ar: {
    overview: "نظرة عامة",
    feed: "موجز الاستخبارات",
    graph: "شبكة الانتشار و CIB",
    management: "الروابط والكلمات المفتاحية",
    automation: "مراقبة الأتمتة",
    knowledge: "قاعدة المعرفة",
    audit: "سجلات التدقيق",
    add: "إضافة جديدة",
    sources: "الروابط والمصادر",
    keywords: "الكلمات المفتاحية",
    prompts: "إعدادات الذكاء الاصطناعي",
    signout: "تسجيل الخروج",
  },
  en: {
    overview: "Overview",
    feed: "Intelligence feed",
    graph: "Propagation & CIB",
    management: "Sources & keywords",
    automation: "Automation monitor",
    knowledge: "Knowledge base",
    audit: "Audit logs",
    add: "Add new",
    sources: "Sources",
    keywords: "Keywords",
    prompts: "AI settings",
    signout: "Sign out",
  },
};
class ApiError extends Error {
  status: number;
  constructor(status: number) {
    super(
      status === 401
        ? "انتهت جلسة الدخول."
        : status === 403
          ? "لا تملك صلاحية لهذا الإجراء."
          : status === 422
            ? "تحقق من البيانات المدخلة."
            : "تعذر إكمال الطلب.",
    );
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
  if (!response.ok) throw new ApiError(response.status);
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
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(false);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const response = await fetch(`${API}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) throw new ApiError(response.status);
      const data = (await response.json()) as {
        access_token: string;
        role: Role;
      };
      onLogin(data.access_token, data.role);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذر تسجيل الدخول");
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
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button login-button" type="submit">
          {lang === "ar" ? "تسجيل الدخول" : "Sign in"}{" "}
          <ArrowUpRight size={16} />
        </button>
      </form>
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
function Dashboard({ token, lang: language }: { token: string; lang: Lang }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [posts, setPosts] = useState<Post[]>([]);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [selectedTopicId, setSelectedTopicId] = useState<number | null>(null);
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
    Promise.all([
      get<Stats>("/api/dashboard/stats", token),
      get<Post[]>("/api/dashboard/recent-activity", token),
      get<AiStatus>("/api/ai/status", token),
      get<Topic[]>("/api/v1/topics", token),
    ])
      .then(([s, p, ai, nextTopics]) => {
        setStats(s);
        setPosts(p);
        setAiStatus(ai);
        setTopics(nextTopics);
        setSelectedTopicId((current) => current ?? nextTopics[0]?.id ?? null);
        setActivityPage(1);
      })
      .catch(() =>
        setError(
          language === "ar" ? "تعذر تحميل البيانات." : "Unable to load data.",
        ),
      );
  }, [token, language]);

  useEffect(() => {
    if (!selectedTopicId) return;
    get<{ alerts: AlertItem[]; summary?: AlertSummary }>(`/api/v1/analytics/topics/${selectedTopicId}/alerts`, token)
      .then((payload) => setAlerts(payload.alerts ?? []))
      .catch(() => setAlerts([]));
  }, [selectedTopicId, token]);

  const exportReport = async (format: "pdf" | "csv" | "json" | "xlsx") => {
    if (!selectedTopicId) return;
    const response = await fetch(`${API}/api/v1/analytics/topics/${selectedTopicId}/reports/executive-pdf`, {
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
          <button type="button" className="primary-button" onClick={() => void exportReport("pdf")}>Export Executive PDF</button>
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
              <p className="loading-text">جار التحميل...</p>
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
          <div className="activity-row" key={post.id}>
            <span className="source-mark source-cyan">
              {post.platform[0]?.toUpperCase()}
            </span>
            <span className="activity-main">
              <strong>{post.title || post.content.slice(0, 100)}</strong>
              <small>
                {post.author} ·{" "}
                {new Date(post.scraped_at).toLocaleString(
                  language === "ar" ? "ar-EG" : "en-US",
                )}
              </small>
            </span>
            <span className="badge badge-neutral">
              {post.severity_level || "غير محلل"}
            </span>
          </div>
        ))}
        {posts.length > 0 && (
          <div className="pagination">
            <button
              className="secondary-button"
              disabled={activityPage === 1}
              onClick={() => setActivityPage(activityPage - 1)}
            >
              السابق
            </button>
            <span>
              صفحة {activityPage} من {activityPageCount}
            </span>
            <button
              className="secondary-button"
              disabled={activityPage === activityPageCount}
              onClick={() => setActivityPage(activityPage + 1)}
            >
              التالي
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
function PostDetailDialog({
  post,
  token,
  onClose,
}: {
  post: Post;
  token: string;
  onClose: () => void;
}) {
  const [logs, setLogs] = useState<AuditRecord[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const loadLogs = () =>
    get<AuditRecord[]>(
      `/api/v1/audit-logs/topics/${post.topic_id}?limit=100`,
      token,
    )
      .then((records) =>
        setLogs(records.filter((record) => record.post_id === post.id)),
      )
      .catch(() => setError("تعذر تحميل نشاط الخبر."));
  useEffect(() => {
    void loadLogs();
  }, [post.id, post.topic_id, token]);
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
      setError("تعذر تحديث أولوية الخبر.");
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="post-dialog" onClick={(event) => event.stopPropagation()}>
        <button className="icon-button" onClick={onClose}>
          <X size={18} />
        </button>
        <p className="eyebrow">{post.platform}</p>
        <h2>{post.title || "منشور بدون عنوان"}</h2>
        <p className="dialog-source">
          {post.author} · {new Date(post.scraped_at).toLocaleString("ar-EG")}
        </p>
        <p className="dialog-content">{post.content}</p>
        <div className="config-actions">
          <button
            className={`icon-button ${post.is_important ? "priority-active" : ""}`}
            title="مهم"
            aria-label="وضع علامة مهم"
            disabled={saving}
            onClick={() => mark("is_important")}
          >
            <Star size={16} />
          </button>
          <button
            className={`icon-button ${post.is_dangerous ? "danger-active" : ""}`}
            title="خطير"
            aria-label="وضع علامة خطير"
            disabled={saving}
            onClick={() => mark("is_dangerous")}
          >
            <AlertTriangle size={16} />
          </button>
        </div>
        {error && <div className="data-error">{error}</div>}
        {post.media_urls?.length ? (
          <div className="media-grid">
            {post.media_urls.map((media, index) =>
              typeof media === "string" && /\.(mp4|webm)(\?|$)/i.test(media) ? (
                <video key={index} src={media} controls />
              ) : typeof media === "string" ? (
                <img key={index} src={media} alt="وسائط الخبر" />
              ) : null,
            )}
          </div>
        ) : (
          <div className="media-empty">لا توجد صورة أو فيديو لهذا الخبر.</div>
        )}
        {post.post_url && (
          <a
            className="wide-ghost"
            href={post.post_url}
            target="_blank"
            rel="noreferrer"
          >
            فتح المصدر الأصلي <ArrowUpRight size={15} />
          </a>
        )}
        <div className="dialog-activity">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Activity</p>
              <h3>نشاط المستخدمين</h3>
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
                          .join("، ")
                      : ""}
                  </small>
                </span>
                <small>
                  {new Date(log.created_at).toLocaleString("ar-EG")}
                </small>
              </div>
            ))
          ) : (
            <div className="empty-state">لا يوجد نشاط مسجل لهذا الخبر.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function Feed({ token, lang }: { token: string; lang: Lang }) {
  const [posts, setPosts] = useState<Post[]>([]);
  const [range, setRange] = useState("day");
  const [keyword, setKeyword] = useState("");
  const [selected, setSelected] = useState<Post | null>(null);
  const [now, setNow] = useState(0);
  const [filtered, setFiltered] = useState<Post[]>([]);
  const [feedPage, setFeedPage] = useState(1);
  const feedPageSize = 5;
  const feedPageCount = Math.max(1, Math.ceil(filtered.length / feedPageSize));
  const visibleFeedPosts = filtered.slice(
    (feedPage - 1) * feedPageSize,
    feedPage * feedPageSize,
  );
  useEffect(() => {
    const timer = window.setTimeout(() => setNow(new Date().getTime()), 0);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => {
    get<Post[]>("/api/data/posts/latest?limit=500", token)
      .then(setPosts)
      .catch(() => setPosts([]));
  }, [token]);
  const durations: Record<string, number> = {
    hour: 3600000,
    day: 86400000,
    week: 604800000,
    month: 2592000000,
    days90: 7776000000,
    year: 31536000000,
  };
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const search = keyword.toLocaleLowerCase();
      setFiltered(
        posts.filter(
          (post) =>
            now - new Date(post.scraped_at).getTime() <= durations[range] &&
            `${post.title ?? ""} ${post.content} ${post.author} ${post.platform}`
              .toLocaleLowerCase()
              .includes(search),
        ),
      );
      setFeedPage(1);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [posts, now, range, keyword]);
  const ranges = [
    ["hour", "آخر ساعة"],
    ["day", "اليوم"],
    ["week", "الأسبوع"],
    ["month", "الشهر"],
    ["days90", "90 يوماً"],
    ["year", "السنة"],
  ];
  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">بيانات مباشرة</p>
          <h1>{lang === "ar" ? "موجز الاستخبارات" : "Intelligence feed"}</h1>
          <p className="subhead">{filtered.length} خبر مطابق للفترة والكلمة.</p>
        </div>
        <button className="primary-button">
          <Plus size={16} /> {lang === "ar" ? "إضافة" : "Add"}
        </button>
      </div>
      <div className="feed-filters">
        <label className="search-field">
          <Search size={17} />
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="فلترة بالكلمات المفتاحية"
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
      </div>
      <div className="feed-items">
        {visibleFeedPosts.map((post) => (
          <button
            className="feed-card"
            key={post.id}
            onClick={() => setSelected(post)}
          >
            <div className="feed-art art-cyan">
              <span>{post.platform}</span>
              <Globe2 size={30} />
            </div>
            <div className="feed-body">
              <div className="feed-meta">
                <span>{post.author}</span>
                <span>{new Date(post.scraped_at).toLocaleString("ar-EG")}</span>
              </div>
              <h3>{post.title || post.content.slice(0, 120)}</h3>
              <p>{post.content.slice(0, 240)}</p>
              <span className="badge badge-neutral">
                {post.severity_level || "غير محلل"}
              </span>
            </div>
          </button>
        ))}
      </div>
      {filtered.length > 0 && (
        <div className="pagination">
          <button
            className="secondary-button"
            disabled={feedPage === 1}
            onClick={() => setFeedPage((page) => page - 1)}
          >
            السابق
          </button>
          <span>صفحة {feedPage} من {feedPageCount}</span>
          <button
            className="secondary-button"
            disabled={feedPage === feedPageCount}
            onClick={() => setFeedPage((page) => page + 1)}
          >
            التالي
          </button>
        </div>
      )}
      {selected && (
        <PostDetailDialog
          post={selected}
          token={token}
          onClose={() => setSelected(null)}
        />
      )}
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
  const [actorId, setActorId] = useState("");
  const [topics, setTopics] = useState<Topic[]>([]);
  const [topicId, setTopicId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const platforms = [
    ["rss", "RSS"],
    ["telegram", "تيليجرام"],
    ["facebook", "فيسبوك"],
    ["reddit", "ريديت"],
    ["youtube", "يوتيوب"],
  ] as const;
  const pageSize = 5;
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const visibleItems = items.slice((page - 1) * pageSize, page * pageSize);
  const load = (selectedTopicId = topicId) => {
    if (!selectedTopicId) return;
    void get<Item[]>(`/api/v1/topics/${selectedTopicId}/${tab}`, token)
      .then(setItems)
      .catch((cause) => {
        setItems([]);
        setError(
          cause instanceof ApiError ? cause.message : "تعذر تحميل البيانات.",
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
          cause instanceof ApiError ? cause.message : "تعذر تحميل المواضيع.",
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
    setActorId("");
    setError("");
    setFormOpen(true);
  };
  const openEdit = (item: Item) => {
    setEditingItem(item);
    setName(item.name ?? "");
    setPlatform(item.platform ?? "rss");
    setValue(item.url_or_handle ?? item.word_or_phrase ?? "");
    setActorId(item.apify_actor_id ?? "");
    setError("");
    setFormOpen(true);
  };
  const remove = async (item: Item) => {
    if (!topicId || !window.confirm("هل تريد حذف هذا السجل؟")) return;
    try {
      await request<void>(
        `/api/v1/topics/${topicId}/${tab}/${item.id}`,
        token,
        { method: "DELETE" },
      );
      if (visibleItems.length === 1 && page > 1) setPage(page - 1);
      load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "تعذر حذف السجل.");
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
            apify_actor_id: actorId || null,
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
      setActorId("");
      setEditingItem(null);
      setFormOpen(false);
      load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "تعذر حفظ السجل.");
    }
  };
  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">إعدادات المراقبة</p>
          <h1>إدارة الروابط والكلمات المفتاحية</h1>
          <p className="subhead">إدارة العناصر التي تستخدمها عملية الجمع.</p>
        </div>
        <button className="primary-button" onClick={openCreate}>
          <Plus size={16} /> إضافة جديدة
        </button>
      </div>
      {error && <div className="data-error">{error}</div>}
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
          الروابط والمصادر ({tab === "sources" ? items.length : "..."})
        </button>
        <button
          className={tab === "keywords" ? "selected" : ""}
          onClick={() => setTab("keywords")}
        >
          الكلمات المفتاحية ({tab === "keywords" ? items.length : "..."})
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
              {item.status ?? (item.is_active ? "نشط" : "متوقف")}
            </span>
            <span className="config-actions">
              <button
                className="icon-button"
                title="تعديل"
                aria-label="تعديل"
                onClick={() => openEdit(item)}
              >
                <Edit3 size={15} />
              </button>
              <button
                className="icon-button danger-button"
                title="حذف"
                aria-label="حذف"
                onClick={() => remove(item)}
              >
                <Trash2 size={15} />
              </button>
            </span>
          </div>
        ))}
        {!items.length && (
          <div className="empty-state">لا توجد عناصر مضافة بعد.</div>
        )}
      </div>
      {items.length > 0 && (
        <div className="pagination">
          <button
            className="secondary-button"
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
          >
            السابق
          </button>
          <span>
            صفحة {page} من {pageCount}
          </span>
          <button
            className="secondary-button"
            disabled={page === pageCount}
            onClick={() => setPage(page + 1)}
          >
            التالي
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
                  ? "تعديل السجل"
                  : tab === "sources"
                    ? "إضافة رابط مصدر"
                    : "إضافة كلمة مفتاحية"}
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
                  اسم المصدر
                  <input
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    required
                  />
                </label>
                <label>
                  المنصة
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
                <label>
                  Apify Actor ID
                  <input
                    value={actorId}
                    onChange={(event) => setActorId(event.target.value)}
                    placeholder="اختياري"
                  />
                </label>
              </>
            )}
            <label>
              {tab === "sources" ? "الرابط أو الحساب" : "الكلمة أو العبارة"}
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
                إلغاء
              </button>
              <button type="submit" className="primary-button">
                <Check size={15} /> حفظ
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
  const [templateText, setTemplateText] = useState("حلل المحتوى المرصود حول الموضوع المحدد، وحدد أهم الادعاءات والمخاطر ومستوى الأولوية، ثم قدم ملخصاً واضحاً باللغة العربية.");
  const [name, setName] = useState("تحليل المحتوى");
  const [provider, setProvider] = useState("ollama");
  const [modelName, setModelName] = useState("qwen2.5:7b");
  const [availableModels, setAvailableModels] = useState<string[]>(["qwen2.5:7b", "llama3.1:8b", "mistral:7b"]);
  const [baseUrl, setBaseUrl] = useState("http://localhost:11434");
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
  ];

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
    } catch {
      setTestResult(null);
      setResult(lang === "ar" ? "تعذر اختبار النموذج." : "Prompt test failed.");
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
      const config = await request<{ has_api_key: boolean }>("/api/ai/config", token, {
        method: "PUT",
        body: JSON.stringify({ provider, model: modelName, base_url: baseUrl, api_key: apiKey || null }),
      });
      setHasApiKey(config.has_api_key);
      setConfigured(true);
      setApiKey("");
      setConnectionMessage(lang === "ar" ? "تم حفظ إعدادات الاتصال." : "Connection settings saved.");
    } catch {
      setConnectionMessage(lang === "ar" ? "تعذر حفظ إعدادات الاتصال." : "Unable to save connection settings.");
    }
  };

  const testConnection = async () => {
    try {
      await request("/api/ai/config", token, {
        method: "PUT",
        body: JSON.stringify({ provider, model: modelName, base_url: baseUrl, api_key: apiKey || null }),
      });
      const response = await request<{ models: string[] }>("/api/ai/config/test", token, { method: "POST" });
      setAvailableModels(response.models);
      if (response.models.length && !response.models.includes(modelName)) setModelName(response.models[0]);
      setConnectionMessage(`${lang === "ar" ? "تم الاتصال بنجاح. النماذج المتاحة: " : "Connected. Available models: "}${response.models.length}`);
    } catch {
      setConnectionMessage(lang === "ar" ? "فشل الاتصال. تحقق من الرابط والتوكن." : "Connection failed. Check the URL and token.");
    }
  };

  const fetchModels = async () => {
    try {
      await request("/api/ai/config", token, {
        method: "PUT",
        body: JSON.stringify({ provider, model: modelName, base_url: baseUrl, api_key: apiKey || null }),
      });
      const response = await request<{ models: string[] }>("/api/ai/config/models", token);
      setAvailableModels(response.models);
      setConnectionMessage(lang === "ar" ? `تم جلب ${response.models.length} نموذجاً.` : `Fetched ${response.models.length} models.`);
    } catch {
      setConnectionMessage(lang === "ar" ? "تعذر جلب النماذج." : "Unable to fetch models.");
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
                  const nextProvider = event.target.value;
                  setProvider(nextProvider);
                  setModelName(nextProvider === "ollama" ? "qwen2.5:7b" : nextProvider === "openrouter" ? "openai/gpt-4o-mini" : "gemini-2.0-flash");
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
              <small className="field-help">{lang === "ar" ? "مثال Ollama: http://localhost:11434" : "Example for Ollama: http://localhost:11434"}</small>
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
            <div className="model-info-card"><span className="model-card-label">{lang === "ar" ? "حالة الاعتماد" : "Credential status"}</span><strong>{configured ? (lang === "ar" ? "جاهز" : "Ready") : (lang === "ar" ? "غير مكتمل" : "Incomplete")}</strong><small>{provider === "ollama" ? (lang === "ar" ? "لا يحتاج مفتاح API" : "No API key required") : hasApiKey ? (lang === "ar" ? "مفتاح محفوظ" : "API key saved") : (lang === "ar" ? "أدخل المفتاح" : "Enter an API key")}</small></div>
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
  const onLogin = (nextToken: string, nextRole: Role) => {
    const normalized = ["admin", "topic_admin", "topic_monitor"].includes(nextRole) ? (nextRole === "admin" ? "super_admin" : nextRole === "topic_admin" ? "topic_manager" : "analyst") : nextRole;
    window.localStorage.setItem("signaldesk_token", nextToken);
    window.localStorage.setItem("signaldesk_role", normalized);
    setToken(nextToken);
    setRole(normalized as Role);
  };
  const signOut = () => {
    window.localStorage.removeItem("signaldesk_token");
    window.localStorage.removeItem("signaldesk_role");
    setToken("");
  };
  const toggle = () => {
    const next = lang === "ar" ? "en" : "ar";
    setLang(next);
    document.documentElement.lang = next;
    document.documentElement.dir = next === "ar" ? "rtl" : "ltr";
  };
  const adminRequest = <T,>(path: string, init?: RequestInit) =>
    request<T>(path, token, init);
  if (!token) return <Login lang={lang} onLogin={onLogin} toggle={toggle} />;
  const t = labels[lang];
  const navigationWithAdmin = [
    ...navigation[lang],
    ...(role === "super_admin"
      ? ([
          ["topics", "إدارة المواضيع", Database],
          ["users", "إدارة المستخدمين", Users],
        ] as const)
      : role === "topic_admin"
        ? ([["topics", "إدارة المواضيع", Database]] as const)
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
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button className="nav-item">
            <Settings2 size={18} />
            <span>إعدادات مساحة العمل</span>
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
              (page === "topics" ? "إدارة المواضيع" : "إدارة المستخدمين")}
          </div>
          <div className="topbar-actions">
            <label className="global-search">
              <Search size={17} />
              <input placeholder={lang === "ar" ? "بحث" : "Search"} />
            </label>
            <button className="language-button" onClick={toggle}>
              {lang === "ar" ? "English" : "العربية"}
            </button>
            <span className="top-avatar">AM</span>
          </div>
        </header>
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
          <PropagationGraphView topicId={1} request={adminRequest} lang={lang} />
        ) : page === "management" ? (
          <Monitoring token={token} lang={lang} />
        ) : page === "automation" ? (
          <AutomationMonitor token={token} role={role} lang={lang} />
        ) : page === "knowledge" ? (
          <KnowledgeBase token={token} lang={lang} />
        ) : page === "topics" ? (
          <TopicManagement request={adminRequest} role={role} />
        ) : page === "users" ? (
          <UserManagement request={adminRequest} role={role} />
        ) : page === "audit" ? (
          <AuditDashboard request={adminRequest} role={role} />
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
    </main>
  );
}
const navigation = {
  ar: [
    ["overview", "نظرة عامة", LayoutDashboard],
    ["feed", "موجز الاستخبارات", Radio],
    ["graph", "شبكة الانتشار و CIB", Share2],
    ["automation", "مراقبة الأتمتة", Activity],
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
