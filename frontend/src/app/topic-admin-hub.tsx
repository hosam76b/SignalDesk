'use client'

import { TopicManagement } from './admin-topics'
import { TopicMembers } from './topic-members'

type Role = 'super_admin' | 'topic_admin' | 'topic_monitor'
type Lang = 'ar' | 'en'
type Request = <T>(path: string, init?: RequestInit) => Promise<T>

export function TopicAdminHub({ request, role, lang }: { request: Request; role: Role; lang: Lang }) {
  return <><TopicManagement request={request} role={role} lang={lang}/><TopicMembers request={request} role={role} lang={lang}/></>
}
