"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useEffect, useState } from "react";
import { Check, Edit3, Plus, Trash2, X } from "lucide-react";

type Role = "super_admin" | "topic_admin" | "topic_monitor";
type Lang = "ar" | "en";
type Topic = { id: number; title: string };
type User = {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  topic_ids: number[];
};
type Request = <T>(path: string, init?: RequestInit) => Promise<T>;

const roleNames: Record<Role, string> = {
  super_admin: "SuperAdmin",
  topic_admin: "TopicAdmin",
  topic_monitor: "Monitor",
};

export function UserManagement({
  request,
  role,
  lang,
}: {
  request: Request;
  role: Role;
  lang: Lang;
}) {
  const [users, setUsers] = useState<User[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [editing, setEditing] = useState<User | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    email: "",
    password: "",
    full_name: "",
    role: "topic_monitor" as Role,
    topicId: "",
  });
  const load = async () => {
    try {
      const [nextUsers, nextTopics] = await Promise.all([
        request<User[]>("/api/users"),
        request<Topic[]>("/api/v1/topics"),
      ]);
      setUsers(
        nextUsers.map((user) => ({ ...user, topic_ids: user.topic_ids ?? [] })),
      );
      setTopics(nextTopics);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر تحميل المستخدمين." : "Unable to load users."),
      );
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      const user = editing
        ? await request<User>(`/api/users/${editing.id}`, {
            method: "PUT",
            body: JSON.stringify({
              full_name: form.full_name,
              role: form.role,
            }),
          })
        : await request<User>("/api/users", {
            method: "POST",
            body: JSON.stringify({
              email: form.email,
              password: form.password,
              full_name: form.full_name,
              role: form.role,
            }),
          });
      if (form.topicId && form.role !== "super_admin")
        await request(`/api/v1/topics/${form.topicId}/assign-user`, {
          method: "POST",
          body: JSON.stringify({ user_id: user.id, role: form.role }),
        });
      setOpen(false);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر حفظ المستخدم." : "Unable to save the user."));
    }
  };
  const remove = async (user: User) => {
    if (!window.confirm(lang === "ar" ? `حذف المستخدم ${user.email}؟` : `Delete user ${user.email}?`)) return;
    try {
      await request(`/api/users/${user.id}`, { method: "DELETE" });
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === "ar" ? "تعذر حذف المستخدم." : "Unable to delete the user."));
    }
  };
  const openCreate = () => {
    setEditing(null);
    setForm({
      email: "",
      password: "",
      full_name: "",
      role: "topic_monitor",
      topicId: "",
    });
    setError("");
    setOpen(true);
  };
  const openEdit = (user: User) => {
    setEditing(user);
    setForm({
      email: user.email,
      password: "",
      full_name: user.full_name,
      role: user.role,
      topicId: user.topic_ids[0]?.toString() ?? "",
    });
    setError("");
    setOpen(true);
  };
  if (role !== "super_admin")
    return (
      <div className="page-content">
        <div className="data-error">{lang === "ar" ? "لا تملك صلاحية إدارة المستخدمين." : "You don't have permission to manage users."}</div>
      </div>
    );
  return (
    <div className="page-content user-management-page">
      <div className="page-header">
        <div className="user-page-title">
          <p className="eyebrow">RBAC</p>
          <h1>{lang === "ar" ? "إدارة المستخدمين" : "User management"}</h1>
          <p className="subhead">{lang === "ar" ? "المستخدمون والأدوار والمواضيع المعيّنة." : "Users, roles, and assigned topics."}</p>
        </div>
        <button className="primary-button" onClick={openCreate}>
          <Plus size={16} /> {lang === "ar" ? "مستخدم جديد" : "New user"}
        </button>
      </div>
      {error && <div className="data-error">{error}</div>}
      <div className="panel user-table">
        <div className="table-head">
          <span>{lang === "ar" ? "المستخدم" : "User"}</span>
          <span>{lang === "ar" ? "الدور" : "Role"}</span>
          <span>{lang === "ar" ? "المواضيع" : "Topics"}</span>
          <span>{lang === "ar" ? "الحالة" : "Status"}</span>
          <span />
        </div>
        {users.map((user) => (
          <div className="user-row" key={user.id}>
            <div className="user-id">
              <span className="avatar avatar-cyan">{user.full_name[0]}</span>
              <span>
                <strong>{user.full_name}</strong>
                <small>{user.email}</small>
              </span>
            </div>
            <span>{roleNames[user.role]}</span>
            <span>
              {user.topic_ids
                .map(
                  (id) =>
                    topics.find((topic) => topic.id === id)?.title ?? `#${id}`,
                )
                .join(lang === "ar" ? "، " : ", ") || (lang === "ar" ? "عالمي" : "Global")}
            </span>
            <span className="badge badge-neutral">
              {user.is_active ? (lang === "ar" ? "نشط" : "Active") : (lang === "ar" ? "متوقف" : "Disabled")}
            </span>
            <span className="config-actions user-actions">
              <button
                className="icon-button"
                title={lang === "ar" ? "تعديل المستخدم" : "Edit user"}
                aria-label={lang === "ar" ? "تعديل المستخدم" : "Edit user"}
                onClick={() => openEdit(user)}
              >
                <Edit3 size={15} />
              </button>
              <button
                className="icon-button danger-button"
                title={lang === "ar" ? "حذف المستخدم" : "Delete user"}
                aria-label={lang === "ar" ? "حذف المستخدم" : "Delete user"}
                onClick={() => remove(user)}
              >
                <Trash2 size={15} />
              </button>
            </span>
          </div>
        ))}
      </div>
      {open && (
        <div className="modal-backdrop" onClick={() => setOpen(false)}>
          <form
            className="source-modal"
            onSubmit={save}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-heading">
              <h2>{editing ? (lang === "ar" ? "تعديل المستخدم" : "Edit user") : (lang === "ar" ? "إنشاء مستخدم" : "Create user")}</h2>
              <button
                type="button"
                className="icon-button"
                onClick={() => setOpen(false)}
              >
                <X size={18} />
              </button>
            </div>
            {!editing && (
              <>
                <label>
                  {lang === "ar" ? "البريد الإلكتروني" : "Email"}
                  <input
                    type="email"
                    value={form.email}
                    onChange={(event) =>
                      setForm({ ...form, email: event.target.value })
                    }
                    required
                  />
                </label>
                <label>
                  {lang === "ar" ? "كلمة المرور" : "Password"}
                  <input
                    type="password"
                    value={form.password}
                    onChange={(event) =>
                      setForm({ ...form, password: event.target.value })
                    }
                    required
                  />
                </label>
              </>
            )}
            <label>
              {lang === "ar" ? "الاسم" : "Name"}
              <input
                value={form.full_name}
                onChange={(event) =>
                  setForm({ ...form, full_name: event.target.value })
                }
                required
              />
            </label>
            <label>
              {lang === "ar" ? "الدور" : "Role"}
              <select
                value={form.role}
                onChange={(event) =>
                  setForm({ ...form, role: event.target.value as Role })
                }
              >
                {Object.entries(roleNames).map(([value, label]) => (
                  <option value={value} key={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            {form.role !== "super_admin" && (
              <label>
                {lang === "ar" ? "الموضوع" : "Topic"}
                <select
                  value={form.topicId}
                  onChange={(event) =>
                    setForm({ ...form, topicId: event.target.value })
                  }
                  required
                >
                  <option value="">{lang === "ar" ? "اختر موضوعاً" : "Choose a topic"}</option>
                  {topics.map((topic) => (
                    <option value={topic.id} key={topic.id}>
                      {topic.title}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setOpen(false)}
              >
                {lang === "ar" ? "إلغاء" : "Cancel"}
              </button>
              <button className="primary-button" type="submit">
                <Check size={15} /> {lang === "ar" ? "حفظ" : "Save"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
