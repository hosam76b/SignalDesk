'use client'

import { useEffect, useState } from 'react'
import { Check, SlidersHorizontal, X } from 'lucide-react'

type Lang = 'ar' | 'en'
type Settings = { workspaceName: string; notifications: boolean; autoRefresh: boolean; refreshSeconds: number }
type Request = <T>(path: string, init?: RequestInit) => Promise<T>

const defaults: Settings = { workspaceName: 'Signaldesk', notifications: true, autoRefresh: true, refreshSeconds: 60 }

export function WorkspaceSettings({ lang, request, onLanguageChange }: { lang: Lang; request: Request; onLanguageChange: (language: Lang) => void }) {
  const [settings, setSettings] = useState<Settings>(defaults)
  const [open, setOpen] = useState(false)
  const [apiStatus, setApiStatus] = useState('checking')
  const [saved, setSaved] = useState(false)
  useEffect(() => { const show = () => setOpen(true); const click = (event: MouseEvent) => { const target = event.target as HTMLElement; if (target.closest('.sidebar-bottom .nav-item')?.textContent?.includes('إعدادات مساحة العمل')) setOpen(true) }; window.addEventListener('signaldesk-open-settings', show); document.addEventListener('click', click); try { const stored = window.localStorage.getItem('signaldesk_workspace_settings'); if (stored) setSettings({ ...defaults, ...JSON.parse(stored) }) } catch { setSettings(defaults) }; void request<unknown>('/health').then(() => setApiStatus('online')).catch(() => setApiStatus('offline')); return () => { window.removeEventListener('signaldesk-open-settings', show); document.removeEventListener('click', click) } }, [])
  const update = <K extends keyof Settings>(key: K, value: Settings[K]) => setSettings(current => ({ ...current, [key]: value }))
  const save = () => { window.localStorage.setItem('signaldesk_workspace_settings', JSON.stringify(settings)); window.localStorage.setItem('signaldesk_workspace_name', settings.workspaceName); onLanguageChange(lang); setSaved(true); window.setTimeout(() => setSaved(false), 1800) }
  if (!open) return null
  const close = () => setOpen(false)
  return <div className="modal-backdrop" onClick={close}><section className="source-modal" onClick={event => event.stopPropagation()}><div className="modal-heading"><div><p className="eyebrow">{lang === 'ar' ? 'مساحة العمل' : 'Workspace'}</p><h2>{lang === 'ar' ? 'إعدادات مساحة العمل' : 'Workspace settings'}</h2></div><button className="icon-button" onClick={close} aria-label="إغلاق"><X size={18}/></button></div><label>{lang === 'ar' ? 'اسم مساحة العمل' : 'Workspace name'}<input value={settings.workspaceName} onChange={event => update('workspaceName', event.target.value)} maxLength={80}/></label><label>{lang === 'ar' ? 'لغة الواجهة' : 'Interface language'}<select value={lang} onChange={event => onLanguageChange(event.target.value as Lang)}><option value="ar">العربية</option><option value="en">English</option></select></label><label className="setting-toggle"><span>{lang === 'ar' ? 'إشعارات النظام' : 'System notifications'}</span><input type="checkbox" checked={settings.notifications} onChange={event => update('notifications', event.target.checked)}/></label><label className="setting-toggle"><span>{lang === 'ar' ? 'التحديث التلقائي' : 'Auto refresh'}</span><input type="checkbox" checked={settings.autoRefresh} onChange={event => update('autoRefresh', event.target.checked)}/></label>{settings.autoRefresh && <label>{lang === 'ar' ? 'فترة التحديث بالثواني' : 'Refresh interval in seconds'}<input type="number" min={15} max={3600} value={settings.refreshSeconds} onChange={event => update('refreshSeconds', Number(event.target.value))}/></label>}<div className="settings-status"><SlidersHorizontal size={15}/><span>{lang === 'ar' ? 'حالة اتصال الـBackend' : 'Backend connection'}</span><strong className={apiStatus === 'online' ? 'status-online' : apiStatus === 'offline' ? 'status-offline' : ''}>{apiStatus === 'online' ? (lang === 'ar' ? 'متصل' : 'Online') : apiStatus === 'offline' ? (lang === 'ar' ? 'غير متصل' : 'Offline') : (lang === 'ar' ? 'جار الفحص' : 'Checking')}</strong></div><div className="modal-actions"><button type="button" className="secondary-button" onClick={close}>{lang === 'ar' ? 'إلغاء' : 'Cancel'}</button><button type="button" className="primary-button" onClick={save}>{saved ? <Check size={15}/> : null}{saved ? (lang === 'ar' ? 'تم الحفظ' : 'Saved') : (lang === 'ar' ? 'حفظ الإعدادات' : 'Save settings')}</button></div></section></div>
}
