"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useEffect, useState } from "react";
import { Check, Edit3, FileText, Plus, Trash2, X } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

type Role = "super_admin" | "topic_admin" | "topic_manager" | "topic_monitor";
type Lang = "ar" | "en";
type Topic = { id: number; title: string; description?: string | null };
type Item = {
  id: number;
  name?: string;
  platform?: string;
  url_or_handle?: string;
  word_or_phrase?: string;
  category?: string;
  apify_actor_id?: string | null;
  status?: string;
  last_error?: string | null;
  last_error_at?: string | null;
  is_active: boolean;
};
type Request = <T>(path: string, init?: RequestInit) => Promise<T>;

export function TopicManagement({
  request,
  role,
  lang,
}: {
  request: Request;
  role: Role;
  lang: Lang;
}) {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [selected, setSelected] = useState<Topic | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [tab, setTab] = useState<"sources" | "keywords">("sources");
  const [topicModal, setTopicModal] = useState(false);
  const [itemModal, setItemModal] = useState(false);
  const [editingTopic, setEditingTopic] = useState<Topic | null>(null);
  const [editingItem, setEditingItem] = useState<Item | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [platform, setPlatform] = useState("rss");
  const [actorId, setActorId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const canManage = role === "super_admin" || role === "topic_admin" || role === "topic_manager";
  const loadTopics = async () => {
    try {
      const next = await request<Topic[]>("/api/v1/topics");
      setTopics(next);
      setSelected((current) =>
        current && next.some((topic) => topic.id === current.id)
          ? current
          : (next[0] ?? null),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر تحميل المواضيع." : "Unable to load topics."));
    }
  };
  const loadItems = async () => {
    if (!selected) return;
    try {
      setItems(await request<Item[]>(`/api/v1/topics/${selected.id}/${tab}`));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر تحميل الموارد." : "Unable to load resources."));
    }
  };
  useEffect(() => {
    void loadTopics();
  }, []);
  useEffect(() => {
    void loadItems();
  }, [selected?.id, tab]);
  const saveTopic = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      await request<Topic>(
        editingTopic ? `/api/v1/topics/${editingTopic.id}` : "/api/v1/topics",
        {
          method: editingTopic ? "PUT" : "POST",
          body: JSON.stringify({
            title: title.trim(),
            description: description.trim() || null,
          }),
        },
      );
      setTopicModal(false);
      setEditingTopic(null);
      await loadTopics();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر حفظ الموضوع." : "Unable to save the topic."));
    }
  };
  const removeTopic = async (topic: Topic) => {
    if (!window.confirm(lang === "ar" ? "حذف هذا الموضوع؟" : "Delete this topic?")) return;
    try {
      await request(`/api/v1/topics/${topic.id}`, { method: "DELETE" });
      await loadTopics();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر حذف الموضوع." : "Unable to delete the topic."));
    }
  };
  const saveItem = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    const body =
      tab === "sources"
        ? {
            name: name.trim(),
            platform,
            url_or_handle: value.trim(),
            target_type: "url",
            apify_actor_id: actorId.trim() || null,
            is_active: true,
          }
        : {
            word_or_phrase: value.trim(),
            category: "general",
            is_active: true,
          };
    try {
      await request(
        editingItem
          ? `/api/v1/topics/${selected.id}/${tab}/${editingItem.id}`
          : `/api/v1/topics/${selected.id}/${tab}`,
        { method: editingItem ? "PUT" : "POST", body: JSON.stringify(body) },
      );
      setItemModal(false);
      await loadItems();
      setError("");
      setNotice(editingItem
        ? (lang === "ar" ? "تم تحديث السجل بنجاح." : "Record updated successfully.")
        : tab === "sources"
          ? (lang === "ar" ? "تم حفظ الرابط بنجاح." : "Source saved successfully.")
          : (lang === "ar" ? "تم حفظ الكلمة المفتاحية بنجاح." : "Keyword saved successfully."));
    } catch (cause) {
      setNotice("");
      const message = cause instanceof Error ? cause.message : "";
      setError(message === "Source URL or handle already exists"
        ? (lang === "ar" ? "الرابط أو الحساب مضاف بالفعل، ولم يتم حفظه مرة أخرى." : "This URL or handle already exists and was not saved again.")
        : message || (lang === "ar" ? "تعذر حفظ المورد." : "Unable to save the resource."));
    }
  };
  const openTopic = (topic?: Topic) => {
    setEditingTopic(topic ?? null);
    setTitle(topic?.title ?? "");
    setDescription(topic?.description ?? "");
    setTopicModal(true);
  };
  const openItem = (item?: Item) => {
    setEditingItem(item ?? null);
    setName(item?.name ?? "");
    setPlatform(item?.platform ?? "rss");
    setValue(item?.url_or_handle ?? item?.word_or_phrase ?? "");
    setActorId(item?.apify_actor_id ?? "");
    setError("");
    setNotice("");
    setItemModal(true);
  };
  const exportPdf = async (tId: number, tTitle: string) => {
    try {
      const token = window.localStorage.getItem("signaldesk_token") || "";
      const response = await fetch(`${API}/api/v1/topics/${tId}/export-pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error(lang === "ar" ? "تعذر إنشاء تقرير PDF" : "Unable to generate the PDF report");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `intelligence_report_topic_${tId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر تصدير تقرير PDF." : "Unable to export the PDF report."));
    }
  };
  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <p className="eyebrow">Topics</p>
          <h1>{lang === "ar" ? "إدارة المواضيع" : "Topic management"}</h1>
          <p className="subhead">{lang === "ar" ? "تخصيص المصادر والكلمات لكل موضوع." : "Customize sources and keywords for each topic."}</p>
        </div>
        {role === "super_admin" && (
          <button className="primary-button" onClick={() => openTopic()}>
            <Plus size={16} /> {lang === "ar" ? "موضوع جديد" : "New topic"}
          </button>
        )}
      </div>
      {error && <div className="data-error">{error}</div>}
      {notice && <div className="connection-message">{notice}</div>}
      <div className="access-grid">
        <div className="panel config-list">
          {topics.map((topic) => (
            <div className="config-row" key={topic.id}>
              <button
                className={`nav-item ${selected?.id === topic.id ? "active" : ""}`}
                onClick={() => setSelected(topic)}
              >
                <span>{topic.title}</span>
              </button>
              {role === "super_admin" && (
                <span className="config-actions">
                  <button
                    className="icon-button"
                    aria-label={lang === "ar" ? "تعديل الموضوع" : "Edit topic"}
                    onClick={() => openTopic(topic)}
                  >
                    <Edit3 size={15} />
                  </button>
                  <button
                    className="icon-button danger-button"
                    aria-label={lang === "ar" ? "حذف الموضوع" : "Delete topic"}
                    onClick={() => removeTopic(topic)}
                  >
                    <Trash2 size={15} />
                  </button>
                </span>
              )}
            </div>
          ))}
        </div>
        {selected && (
          <div className="panel config-list">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">{selected.title}</p>
                <h2>{selected.description || (lang === "ar" ? "موارد الموضوع" : "Topic resources")}</h2>
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => exportPdf(selected.id, selected.title)}
                  title={lang === "ar" ? "تصدير تقرير استخباراتي تنفيذي بصيغة PDF" : "Export an executive intelligence report as PDF"}
                  style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}
                >
                  <FileText size={15} color="#3b82f6" /> {lang === "ar" ? "تصدير تقرير PDF" : "Export PDF report"}
                </button>
                {canManage && (
                  <button className="primary-button" onClick={() => openItem()}>
                    <Plus size={15} /> {lang === "ar" ? "إضافة" : "Add"}
                  </button>
                )}
              </div>
            </div>
            <div className="config-tabs">
              <button
                className={tab === "sources" ? "selected" : ""}
                onClick={() => setTab("sources")}
              >
                {lang === "ar" ? "المصادر" : "Sources"} ({tab === "sources" ? items.length : "..."})
              </button>
              <button
                className={tab === "keywords" ? "selected" : ""}
                onClick={() => setTab("keywords")}
              >
                {lang === "ar" ? "الكلمات" : "Keywords"} ({tab === "keywords" ? items.length : "..."})
              </button>
            </div>
            {items.map((item) => (
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
                  {tab === "sources" && item.last_error && (
                    <small className="source-error-note" title={item.last_error}>
                      {lang === "ar" ? "تعذر الجلب:" : "Fetch failed:"} {item.last_error}
                    </small>
                  )}
                </span>
                {tab === "sources" && item.status === "failed" && (
                  <span className="badge source-failed-badge">{lang === "ar" ? "فشل الجلب" : "Fetch failed"}</span>
                )}
                {canManage && (
                  <span className="config-actions">
                    <button
                      className="icon-button"
                      aria-label={lang === "ar" ? "تعديل المورد" : "Edit resource"}
                      onClick={() => openItem(item)}
                    >
                      <Edit3 size={15} />
                    </button>
                    <button
                      className="icon-button danger-button"
                      aria-label={lang === "ar" ? "حذف المورد" : "Delete resource"}
                      onClick={() =>
                        request(
                          `/api/v1/topics/${selected.id}/${tab}/${item.id}`,
                          { method: "DELETE" },
                        )
                          .then(async () => {
                            await loadItems();
                            setError("");
                            setNotice(lang === "ar" ? "تم حذف السجل." : "Record deleted.");
                          })
                          .catch((cause) => {
                            setNotice("");
                            setError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر حذف المورد." : "Unable to delete the resource."));
                          })
                      }
                    >
                      <Trash2 size={15} />
                    </button>
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      {topicModal && (
        <div className="modal-backdrop" onClick={() => setTopicModal(false)}>
          <form
            className="source-modal"
            onSubmit={saveTopic}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-heading">
              <h2>{editingTopic ? (lang === "ar" ? "تعديل الموضوع" : "Edit topic") : (lang === "ar" ? "إنشاء موضوع" : "Create topic")}</h2>
              <button
                type="button"
                className="icon-button"
                onClick={() => setTopicModal(false)}
              >
                <X size={18} />
              </button>
            </div>
            <label>
              {lang === "ar" ? "اسم الموضوع" : "Topic name"}
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                required
              />
            </label>
            <label>
              {lang === "ar" ? "الوصف" : "Description"}
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            <button className="primary-button" type="submit">
              <Check size={15} /> {lang === "ar" ? "حفظ" : "Save"}
            </button>
          </form>
        </div>
      )}
      {itemModal && selected && (
        <div className="modal-backdrop" onClick={() => setItemModal(false)}>
          <form
            className="source-modal"
            onSubmit={saveItem}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-heading">
              <h2>{editingItem ? (lang === "ar" ? "تعديل المورد" : "Edit resource") : (lang === "ar" ? "إضافة مورد" : "Add resource")}</h2>
              <button
                type="button"
                className="icon-button"
                onClick={() => setItemModal(false)}
              >
                <X size={18} />
              </button>
            </div>
            {error && <div className="data-error">{error}</div>}
            {tab === "sources" && (
              <>
                <label>
                  {lang === "ar" ? "الاسم" : "Name"}
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
                    <option value="rss">RSS</option>
                    <option value="telegram">Telegram</option>
                    <option value="facebook">Facebook</option>
                    <option value="reddit">Reddit</option>
                    <option value="youtube">YouTube</option>
                    <option value="x">X (Twitter)</option>
                  </select>
                </label>
                <label>
                  Apify Actor ID
                  <input
                    value={actorId}
                    onChange={(event) => setActorId(event.target.value)}
                  />
                </label>
              </>
            )}
            <label>
              {tab === "sources" ? (lang === "ar" ? "الرابط أو المعرّف" : "URL or handle") : (lang === "ar" ? "الكلمة المفتاحية" : "Keyword")}
              <input
                value={value}
                onChange={(event) => setValue(event.target.value)}
                required
              />
            </label>
            <button className="primary-button" type="submit">
              <Check size={15} /> {lang === "ar" ? "حفظ" : "Save"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
