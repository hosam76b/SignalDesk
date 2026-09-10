'use client'

import { useEffect, useState } from 'react'
import { Check, Eye, EyeOff, X } from 'lucide-react'

type Lang = 'ar' | 'en'
type SourceSettings = {
  metaAccessToken: string;
  metaGraphApiVersion: string;
  metaAppId: string;
  apifyToken: string;
  apifyFacebookActorId: string;
  apifyInstagramActorId: string;
  apifyXActorId: string;
  apifyTikTokActorId: string;
  apifyThreadsActorId: string;
  youtubeApiKey: string;
  redditClientId: string;
  redditClientSecret: string;
  telegramApiId: string;
  telegramApiHash: string;
  rssEnabled: boolean;
  telegramEnabled: boolean;
  youtubeEnabled: boolean;
  redditEnabled: boolean;
  facebookEnabled: boolean;
  instagramEnabled: boolean;
  xEnabled: boolean;
  tiktokEnabled: boolean;
  threadsEnabled: boolean;
}

const defaults: SourceSettings = {
  metaAccessToken: '',
  metaGraphApiVersion: 'v21.0',
  metaAppId: '',
  apifyToken: '',
  apifyFacebookActorId: '',
  apifyInstagramActorId: '',
  apifyXActorId: '',
  apifyTikTokActorId: '',
  apifyThreadsActorId: '',
  youtubeApiKey: '',
  redditClientId: '',
  redditClientSecret: '',
  telegramApiId: '',
  telegramApiHash: '',
  rssEnabled: true,
  telegramEnabled: true,
  youtubeEnabled: true,
  redditEnabled: true,
  facebookEnabled: true,
  instagramEnabled: true,
  xEnabled: true,
  tiktokEnabled: true,
  threadsEnabled: true,
}

export function DataSourceSettings({ lang, onClose }: { lang: Lang; onClose: () => void }) {
  const [settings, setSettings] = useState<SourceSettings>(defaults);
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem('signaldesk_source_settings');
      if (stored) setSettings({ ...defaults, ...JSON.parse(stored) });
    } catch {
      setSettings(defaults);
    }
  }, []);

  const update = <K extends keyof SourceSettings>(key: K, value: SourceSettings[K]) =>
    setSettings(current => ({ ...current, [key]: value }));

  const save = () => {
    window.localStorage.setItem('signaldesk_source_settings', JSON.stringify(settings));
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
  };

  const secret = (key: keyof SourceSettings, label: string) => (
    <label>
      {label}
      <span className="password-input">
        <input
          type={visible[String(key)] ? 'text' : 'password'}
          value={String(settings[key])}
          onChange={event => update(key, event.target.value)}
          placeholder={lang === 'ar' ? 'أدخل القيمة' : 'Enter value'}
        />
        <button
          type="button"
          onClick={() => setVisible(current => ({ ...current, [String(key)]: !current[String(key)] }))}
          aria-label={lang === 'ar' ? 'إظهار أو إخفاء' : 'Show or hide'}
        >
          {visible[String(key)] ? <EyeOff size={16}/> : <Eye size={16}/>}
        </button>
      </span>
    </label>
  );

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="source-modal data-source-settings" onClick={event => event.stopPropagation()}>
        <div className="modal-heading">
          <div>
            <p className="eyebrow">{lang === 'ar' ? 'التكاملات' : 'Integrations'}</p>
            <h2>{lang === 'ar' ? 'إعدادات مصادر البيانات' : 'Data source settings'}</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label={lang === 'ar' ? 'إغلاق' : 'Close'}><X size={18}/></button>
        </div>
        <p className="settings-note">
          {lang === 'ar'
            ? 'تكامل قنوات Telegram يدعم القنوات العامة مباشرة أو عبر Telethon MTProto API.'
            : 'Telegram channel ingestion supports public channels natively or via Telethon MTProto.'}
        </p>
        {secret('telegramApiId', 'Telegram API ID')}
        {secret('telegramApiHash', 'Telegram API Hash')}
        {secret('metaAccessToken', 'Meta Access Token')}
        <label>Meta Graph API Version<input value={settings.metaGraphApiVersion} onChange={event => update('metaGraphApiVersion', event.target.value)}/></label>
        <label>Meta App ID<input value={settings.metaAppId} onChange={event => update('metaAppId', event.target.value)}/></label>
        {secret('apifyToken', 'Apify API Token')}
        <label>Facebook Actor ID<input value={settings.apifyFacebookActorId} onChange={event => update('apifyFacebookActorId', event.target.value)} placeholder={lang === 'ar' ? 'اختياري' : 'Optional'} /></label>
        <label>Instagram Actor ID<input value={settings.apifyInstagramActorId} onChange={event => update('apifyInstagramActorId', event.target.value)} placeholder={lang === 'ar' ? 'اختياري' : 'Optional'} /></label>
        <label>X / Twitter Actor ID<input value={settings.apifyXActorId} onChange={event => update('apifyXActorId', event.target.value)} placeholder={lang === 'ar' ? 'اختياري' : 'Optional'} /></label>
        <label>TikTok Actor ID<input value={settings.apifyTikTokActorId} onChange={event => update('apifyTikTokActorId', event.target.value)} placeholder={lang === 'ar' ? 'اختياري' : 'Optional'} /></label>
        <label>Threads Actor ID<input value={settings.apifyThreadsActorId} onChange={event => update('apifyThreadsActorId', event.target.value)} placeholder={lang === 'ar' ? 'اختياري' : 'Optional'} /></label>
        <p className="settings-note">
          {lang === 'ar'
            ? 'يتم تحديد Actor المناسب لكل منصة تلقائيًا عند إضافة المصدر، لذلك لا حاجة لإدخاله في كل مرة.'
            : 'The correct actor for each platform is selected automatically when the source is added, so there is no need to enter it every time.'}
        </p>
        {secret('youtubeApiKey', 'YouTube API Key')}
        {secret('redditClientId', 'Reddit Client ID')}
        {secret('redditClientSecret', 'Reddit Client Secret')}
        <div className="source-switches">
          <label className="setting-toggle"><span>RSS</span><input type="checkbox" checked={settings.rssEnabled} onChange={event => update('rssEnabled', event.target.checked)}/></label>
          <label className="setting-toggle"><span>Telegram</span><input type="checkbox" checked={settings.telegramEnabled} onChange={event => update('telegramEnabled', event.target.checked)}/></label>
          <label className="setting-toggle"><span>YouTube</span><input type="checkbox" checked={settings.youtubeEnabled} onChange={event => update('youtubeEnabled', event.target.checked)}/></label>
          <label className="setting-toggle"><span>Reddit</span><input type="checkbox" checked={settings.redditEnabled} onChange={event => update('redditEnabled', event.target.checked)}/></label>
          <label className="setting-toggle"><span>Facebook / Meta</span><input type="checkbox" checked={settings.facebookEnabled} onChange={event => update('facebookEnabled', event.target.checked)}/></label>
          <label className="setting-toggle"><span>Instagram</span><input type="checkbox" checked={settings.instagramEnabled} onChange={event => update('instagramEnabled', event.target.checked)}/></label>
          <label className="setting-toggle"><span>X (Twitter)</span><input type="checkbox" checked={settings.xEnabled} onChange={event => update('xEnabled', event.target.checked)}/></label>
          <label className="setting-toggle"><span>TikTok</span><input type="checkbox" checked={settings.tiktokEnabled} onChange={event => update('tiktokEnabled', event.target.checked)}/></label>
          <label className="setting-toggle"><span>Threads</span><input type="checkbox" checked={settings.threadsEnabled} onChange={event => update('threadsEnabled', event.target.checked)}/></label>
        </div>
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>{lang === 'ar' ? 'إلغاء' : 'Cancel'}</button>
          <button type="button" className="primary-button" onClick={save}>{saved ? <Check size={15}/> : null}{saved ? (lang === 'ar' ? 'تم الحفظ' : 'Saved') : (lang === 'ar' ? 'حفظ الإعدادات' : 'Save settings')}</button>
        </div>
      </section>
    </div>
  );
}
