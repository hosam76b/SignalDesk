'use client'

import { useEffect, useState } from 'react'
import { Check, Eye, EyeOff, X } from 'lucide-react'

type Lang = 'ar' | 'en'
type SourceSettings = {
  metaAccessToken: string;
  metaGraphApiVersion: string;
  metaAppId: string;
  apifyToken: string;
  apifyActorId: string;
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
}

const defaults: SourceSettings = {
  metaAccessToken: '',
  metaGraphApiVersion: 'v21.0',
  metaAppId: '',
  apifyToken: '',
  apifyActorId: 'apify/facebook-posts-scraper',
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
          <button className="icon-button" onClick={onClose} aria-label="إغلاق"><X size={18}/></button>
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
        <label>Apify Actor ID<input value={settings.apifyActorId} onChange={event => update('apifyActorId', event.target.value)}/></label>
        {secret('youtubeApiKey', 'YouTube API Key')}
        {secret('redditClientId', 'Reddit Client ID')}
        {secret('redditClientSecret', 'Reddit Client Secret')}
        <div className="source-switches">
          <label className="setting-toggle"><span>RSS</span><input type="checkbox" checked={settings.rssEnabled} onChange={event => update('rssEnabled', event.target.checked)}/></label>
          <label className="setting-toggle"><span>Telegram</span><input type="checkbox" checked={settings.telegramEnabled} onChange={event => update('telegramEnabled', event.target.checked)}/></label>
          <label className="setting-toggle"><span>YouTube</span><input type="checkbox" checked={settings.youtubeEnabled} onChange={event => update('youtubeEnabled', event.target.checked)}/></label>
          <label className="setting-toggle"><span>Reddit</span><input type="checkbox" checked={settings.redditEnabled} onChange={event => update('redditEnabled', event.target.checked)}/></label>
          <label className="setting-toggle"><span>Facebook / Meta</span><input type="checkbox" checked={settings.facebookEnabled} onChange={event => update('facebookEnabled', event.target.checked)}/></label>
        </div>
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>{lang === 'ar' ? 'إلغاء' : 'Cancel'}</button>
          <button type="button" className="primary-button" onClick={save}>{saved ? <Check size={15}/> : null}{saved ? (lang === 'ar' ? 'تم الحفظ' : 'Saved') : (lang === 'ar' ? 'حفظ الإعدادات' : 'Save settings')}</button>
        </div>
      </section>
    </div>
  );
}
