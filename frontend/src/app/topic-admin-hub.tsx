'use client'

import { TopicManagement } from './admin-topics'
import { TopicMembers } from './topic-members'

type Role = 'super_admin' | 'topic_admin' | 'topic_monitor'
type Request = <T>(path: string, init?: RequestInit) => Promise<T>

export function TopicAdminHub({ request, role }: { request: Request; role: Role }) {
  return <><TopicManagement request={request} role={role}/><TopicMembers request={request} role={role}/></>
}
