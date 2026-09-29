'use client'

import { WorkspaceSettings } from './workspace-settings'
import { apiUrl } from './api-client'

type ApiRequest = <T>(path: string, init?: RequestInit) => Promise<T>

export function WorkspaceSettingsHost() {
  const request: ApiRequest = async <T,>(path: string, init?: RequestInit) => {
    const token = window.localStorage.getItem('signaldesk_token') ?? ''
    const response = await fetch(apiUrl(path), { ...init, headers: { ...Object.fromEntries(new Headers(init?.headers).entries()), Authorization: `Bearer ${token}` }, cache: 'no-store' })
    if (!response.ok) throw new Error(String(response.status))
    return response.json() as Promise<T>
  }

  return <WorkspaceSettings lang="ar" request={request} onLanguageChange={language => { document.documentElement.lang = language; document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr' }} />
}
