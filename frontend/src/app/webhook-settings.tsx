'use client'

import { useCallback, useEffect, useState } from 'react'
import { Check, Eye, EyeOff, ListChecks, Play, Plus, RefreshCw, Trash2, X } from 'lucide-react'

type Lang = 'ar' | 'en'
type RequestFn = <T>(path: string, init?: RequestInit) => Promise<T>

type WebhookItem = {
  id: number
  name: string
  url: string
  has_secret: boolean
  events: string[]
  is_active: boolean
  created_at: string
  updated_at: string
  last_delivery_at: string | null
  last_delivery_success: boolean | null
}

type Delivery = {
  id: number
  webhook_id: number
  event: string
  status_code: number | null
  success: boolean
  error: string | null
  duration_ms: number | null
  created_at: string
}

const EVENTS = ['post_ingested', 'alert_triggered', 'report_ready', 'analysis_completed'] as const

const eventLabels: Record<string, { ar: string; en: string }> = {
  post_ingested: { ar: 'منشور جديد', en: 'New post ingested' },
  alert_triggered: { ar: 'تنبيه مُفعّل', en: 'Alert triggered' },
  report_ready: { ar: 'تقرير جاهز', en: 'Report ready' },
  analysis_completed: { ar: 'اكتمال تحليل AI', en: 'AI analysis completed' },
}

type FormState = { name: string; url: string; secret: string; events: string[]; is_active: boolean }
const emptyForm: FormState = { name: '', url: '', secret: '', events: ['post_ingested'], is_active: true }

export function WebhookSettings({ lang, request, onClose }: { lang: Lang; request: RequestFn; onClose: () => void }) {
  const [webhooks, setWebhooks] = useState<WebhookItem[]>([])
  const [loading, setLoading] = useState(true)
  const [forbidden, setForbidden] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [showSecret, setShowSecret] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testResults, setTestResults] = useState<Record<number, string>>({})
  const [deliveriesFor, setDeliveriesFor] = useState<number | null>(null)
  const [deliveries, setDeliveries] = useState<Delivery[]>([])

  const t = useCallback((ar: string, en: string) => (lang === 'ar' ? ar : en), [lang])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await request<WebhookItem[]>('/api/webhooks')
      setWebhooks(data)
      setForbidden(false)
      setError('')
    } catch (err) {
      if (String(err).includes('403')) setForbidden(true)
      else setError(t('تعذر تحميل إعدادات الويب هوك', 'Failed to load webhook settings'))
    } finally {
      setLoading(false)
    }
  }, [request, t])

  useEffect(() => { void load() }, [load])

  const flash = (message: string) => { setNotice(message); window.setTimeout(() => setNotice(''), 2500) }

  const openCreate = () => { setForm(emptyForm); setEditingId(null); setFormOpen(true); setShowSecret(false) }
  const openEdit = (item: WebhookItem) => {
    setForm({ name: item.name, url: item.url, secret: '', events: item.events, is_active: item.is_active })
    setEditingId(item.id)
    setFormOpen(true)
    setShowSecret(false)
  }

  const toggleEvent = (eventName: string) =>
    setForm(current => ({
      ...current,
      events: current.events.includes(eventName)
        ? current.events.filter(name => name !== eventName)
        : [...current.events, eventName],
    }))

  const save = async () => {
    if (!form.name.trim() || !form.url.trim() || form.events.length === 0) {
      setError(t('أدخل الاسم والرابط واختر حدثاً واحداً على الأقل', 'Enter a name, a URL, and pick at least one event'))
      return
    }
    setSaving(true)
    setError('')
    try {
      const body: Record<string, unknown> = { name: form.name.trim(), url: form.url.trim(), events: form.events, is_active: form.is_active }
      if (form.secret) body.secret = form.secret
      if (editingId === null) {
        await request<WebhookItem>('/api/webhooks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      } else {
        await request<WebhookItem>(`/api/webhooks/${editingId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      }
      setFormOpen(false)
      flash(t('تم حفظ الويب هوك', 'Webhook saved'))
      await load()
    } catch (err) {
      setError(String(err).includes('422') ? t('تحقق من الرابط والأحداث المختارة', 'Check the URL and selected events') : t('فشل حفظ الويب هوك', 'Failed to save webhook'))
    } finally {
      setSaving(false)
    }
  }

  const remove = async (item: WebhookItem) => {
    if (!window.confirm(t(`حذف الويب هوك "${item.name}" نهائياً؟`, `Delete webhook "${item.name}" permanently?`))) return
    try {
      await request<unknown>(`/api/webhooks/${item.id}`, { method: 'DELETE' })
      flash(t('تم حذف الويب هوك', 'Webhook deleted'))
      await load()
    } catch { setError(t('فشل حذف الويب هوك', 'Failed to delete webhook')) }
  }

  const toggleActive = async (item: WebhookItem) => {
    try {
      await request<WebhookItem>(`/api/webhooks/${item.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !item.is_active }),
      })
      await load()
    } catch { setError(t('فشل تحديث الحالة', 'Failed to update status')) }
  }

  const test = async (item: WebhookItem) => {
    setTestResults(current => ({ ...current, [item.id]: t('جار الإرسال…', 'Sending…') }))
    try {
      const result = await request<{ delivered: boolean; status_code?: number | null; error?: string | null }>(`/api/webhooks/${item.id}/test`, { method: 'POST' })
      setTestResults(current => ({
        ...current,
        [item.id]: result.delivered
          ? t(`نجح الإرسال (${result.status_code ?? 200})`, `Delivered (${result.status_code ?? 200})`)
          : `${t('فشل الإرسال', 'Failed')}: ${result.error ?? result.status_code ?? ''}`,
      }))
      await load()
    } catch (err) { setTestResults(current => ({ ...current, [item.id]: `${t('فشل الإرسال', 'Failed')}: ${String(err)}` })) }
  }

  const toggleDeliveries = async (item: WebhookItem) => {
    if (deliveriesFor === item.id) { setDeliveriesFor(null); return }
    setDeliveriesFor(item.id)
    try {
      setDeliveries(await request<Delivery[]>(`/api/webhooks/${item.id}/deliveries?limit=20`))
    } catch { setDeliveries([]) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="source-modal data-source-settings" onClick={event => event.stopPropagation()}>
        <div className="modal-heading">
          <div>
            <p className="eyebrow">{t('التكاملات', 'Integrations')}</p>
            <h2>{t('إعدادات الويب هوك', 'Webhook settings')}</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label={t('إغلاق', 'Close')}><X size={18}/></button>
        </div>

        <p className="settings-note">
          {t(
            'اربط SignalDesk مع n8n أو أي نظام آلي آخر. عند حدوث حدث مشترك به، يُرسَل JSON موقّع إلى الرابط. تحقق في n8n من التوقيع عبر الترويسة X-Webhook-Signature ‏(HMAC-SHA256).',
            'Connect SignalDesk with n8n or any automation tool. Subscribed events are POSTed as signed JSON. Verify requests in n8n via the X-Webhook-Signature header (HMAC-SHA256).'
          )}
        </p>

        {forbidden ? (
          <p className="settings-note">{t('إدارة الويب هوك متاحة للمسؤول الأعلى (super_admin) فقط.', 'Webhook management is available to super admins only.')}</p>
        ) : (
          <>
            {error ? <p className="settings-note" style={{ color: 'var(--danger, #e5534b)' }}>{error}</p> : null}
            {notice ? <p className="settings-note" style={{ color: 'var(--success, #3fb950)' }}><Check size={14}/> {notice}</p> : null}

            {loading ? <p className="settings-note">{t('جار التحميل…', 'Loading…')}</p> : null}

            {!loading && webhooks.length === 0 ? (
              <p className="settings-note">{t('لا توجد ويب هوكات بعد. أضف أول تكامل مع n8n.', 'No webhooks yet. Add your first n8n integration.')}</p>
            ) : null}

            {webhooks.map(item => (
              <div key={item.id} style={{ border: '1px solid var(--border, #30363d)', borderRadius: 10, padding: '10px 12px', marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between' }}>
                  <div style={{ minWidth: 0 }}>
                    <strong>{item.name}</strong>
                    <div style={{ fontSize: 12, opacity: 0.75, direction: 'ltr', textAlign: lang === 'ar' ? 'right' : 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.url}</div>
                  </div>
                  <label className="setting-toggle" style={{ margin: 0 }}>
                    <span>{t('مفعّل', 'Active')}</span>
                    <input type="checkbox" checked={item.is_active} onChange={() => void toggleActive(item)}/>
                  </label>
                </div>

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '8px 0' }}>
                  {item.events.map(eventName => (
                    <span key={eventName} style={{ fontSize: 11, padding: '2px 8px', borderRadius: 999, border: '1px solid var(--border, #30363d)' }}>
                      {eventLabels[eventName] ? t(eventLabels[eventName].ar, eventLabels[eventName].en) : eventName}
                    </span>
                  ))}
                  {item.last_delivery_at ? (
                    <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 999, border: '1px solid var(--border, #30363d)', color: item.last_delivery_success ? 'var(--success, #3fb950)' : 'var(--danger, #e5534b)' }}>
                      {item.last_delivery_success ? t('آخر إرسال ناجح', 'Last delivery OK') : t('آخر إرسال فاشل', 'Last delivery failed')}
                    </span>
                  ) : null}
                </div>

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  <button type="button" className="secondary-button" onClick={() => void test(item)}><Play size={14}/>{t('اختبار', 'Test')}</button>
                  <button type="button" className="secondary-button" onClick={() => openEdit(item)}>{t('تعديل', 'Edit')}</button>
                  <button type="button" className="secondary-button" onClick={() => void toggleDeliveries(item)}><ListChecks size={14}/>{t('السجل', 'Log')}</button>
                  <button type="button" className="secondary-button" onClick={() => void remove(item)}><Trash2 size={14}/>{t('حذف', 'Delete')}</button>
                </div>

                {testResults[item.id] ? <p className="settings-note" style={{ marginTop: 6 }}>{testResults[item.id]}</p> : null}

                {deliveriesFor === item.id ? (
                  <div style={{ marginTop: 8, maxHeight: 180, overflowY: 'auto' }}>
                    {deliveries.length === 0 ? (
                      <p className="settings-note">{t('لا توجد محاولات إرسال مسجلة.', 'No deliveries recorded yet.')}</p>
                    ) : deliveries.map(delivery => (
                      <div key={delivery.id} style={{ fontSize: 12, padding: '4px 0', borderTop: '1px solid var(--border, #30363d)' }}>
                        <span style={{ color: delivery.success ? 'var(--success, #3fb950)' : 'var(--danger, #e5534b)' }}>
                          {delivery.success ? '✓' : '✗'} {delivery.event} {delivery.status_code ? `(${delivery.status_code})` : ''}
                        </span>
                        {' · '}{new Date(delivery.created_at).toLocaleString()}{delivery.duration_ms != null ? ` · ${delivery.duration_ms}ms` : ''}
                        {delivery.error ? <div style={{ opacity: 0.8 }}>{delivery.error}</div> : null}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}

            {!formOpen ? (
              <button type="button" className="secondary-button" onClick={openCreate}><Plus size={15}/>{t('إضافة ويب هوك', 'Add webhook')}</button>
            ) : (
              <div style={{ border: '1px solid var(--border, #30363d)', borderRadius: 10, padding: '10px 12px', marginTop: 10 }}>
                <h3 style={{ marginTop: 0 }}>{editingId === null ? t('ويب هوك جديد', 'New webhook') : t('تعديل الويب هوك', 'Edit webhook')}</h3>
                <label>{t('الاسم', 'Name')}<input value={form.name} onChange={event => setForm(current => ({ ...current, name: event.target.value }))} maxLength={255} placeholder="n8n workflow"/></label>
                <label>{t('الرابط (URL)', 'URL')}<input dir="ltr" value={form.url} onChange={event => setForm(current => ({ ...current, url: event.target.value }))} maxLength={1000} placeholder="https://n8n.example.com/webhook/…"/></label>
                <label>
                  {t('السر التوقيعي (اختياري)', 'Signing secret (optional)')}
                  <span className="password-input">
                    <input
                      type={showSecret ? 'text' : 'password'}
                      dir="ltr"
                      value={form.secret}
                      onChange={event => setForm(current => ({ ...current, secret: event.target.value }))}
                      placeholder={editingId !== null ? t('اتركه فارغاً للإبقاء على الحالي', 'Leave empty to keep current') : t('يُستخدم لتوقيع HMAC', 'Used for HMAC signature')}
                      maxLength={255}
                    />
                    <button type="button" onClick={() => setShowSecret(current => !current)} aria-label={t('إظهار أو إخفاء', 'Show or hide')}>
                      {showSecret ? <EyeOff size={16}/> : <Eye size={16}/>}
                    </button>
                  </span>
                </label>
                <div className="source-switches">
                  {EVENTS.map(eventName => (
                    <label key={eventName} className="setting-toggle">
                      <span>{t(eventLabels[eventName].ar, eventLabels[eventName].en)}</span>
                      <input type="checkbox" checked={form.events.includes(eventName)} onChange={() => toggleEvent(eventName)}/>
                    </label>
                  ))}
                </div>
                <label className="setting-toggle"><span>{t('مفعّل', 'Active')}</span><input type="checkbox" checked={form.is_active} onChange={event => setForm(current => ({ ...current, is_active: event.target.checked }))}/></label>
                <div className="modal-actions">
                  <button type="button" className="secondary-button" onClick={() => setFormOpen(false)}>{t('إلغاء', 'Cancel')}</button>
                  <button type="button" className="primary-button" disabled={saving} onClick={() => void save()}>
                    {saving ? <RefreshCw size={15}/> : <Check size={15}/>}{saving ? t('جار الحفظ…', 'Saving…') : t('حفظ', 'Save')}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
