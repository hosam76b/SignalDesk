'use client'

import { useEffect, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ExternalLink,
  Flame,
  GitFork,
  Radio,
  RefreshCw,
  Search,
  Share2,
  ShieldAlert,
  Users,
} from 'lucide-react'

type Lang = 'ar' | 'en'
type Request = <T>(path: string, init?: RequestInit) => Promise<T>

type GraphNode = {
  id: number
  label: string
  author: string
  platform: string
  source_id: number
  title: string | null
  content_preview: string
  post_url?: string | null
  published_at: string | null
  is_patient_zero: boolean
  is_amplifier: boolean
  severity_level: string
  is_dangerous: boolean
  is_important: boolean
  sentiment: string
  cluster_key: string | null
  cluster_label: string | null
  is_cib: boolean
  delay_from_origin: string
  delay_seconds: number
}

type GraphEdge = {
  id: string
  source: number
  target: number
  origin_id: number
  delay_seconds: number
  delay_formatted: string
  total_delay_formatted: string
  is_coordinated: boolean
  cluster_key: string
  cluster_label: string
}

type GraphData = {
  success: boolean
  topic_id: number
  topic_title: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  summary: {
    total_nodes: number
    total_edges: number
    total_clusters: number
    cib_clusters_count: number
    patient_zero_count: number
    top_amplifiers: Array<{ account: string; amplified_count: number }>
  }
}

export function PropagationGraphView({
  topicId,
  request,
  lang,
}: {
  topicId: number
  request: Request
  lang: Lang
}) {
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [filterCibOnly, setFilterCibOnly] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')

  const loadGraph = async () => {
    setLoading(true)
    try {
      const res = await request<GraphData>(`/api/v1/analytics/topics/${topicId}/propagation-graph`)
      setData(res)
      if (res.nodes && res.nodes.length > 0) {
        setSelectedNode(res.nodes[0])
      }
    } catch {
      try {
        const fallbackRes = await request<GraphData>(`/api/v1/topics/${topicId}/propagation-graph`)
        setData(fallbackRes)
      } catch (err) {
        console.error('Failed to load propagation graph', err)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (topicId) {
      loadGraph()
    }
  }, [topicId])

  const nodes = data?.nodes || []
  const edges = data?.edges || []
  const summary = data?.summary

  const filteredNodes = nodes.filter(node => {
    if (filterCibOnly && !node.is_cib) return false
    if (searchTerm) {
      const term = searchTerm.toLowerCase()
      return (
        node.author.toLowerCase().includes(term) ||
        node.content_preview.toLowerCase().includes(term) ||
        node.platform.toLowerCase().includes(term)
      )
    }
    return true
  })

  const getSeverityColor = (sev: string, isDangerous?: boolean) => {
    if (isDangerous || sev === 'critical') return '#ef4444' // Red
    if (sev === 'high') return '#f97316' // Orange
    if (sev === 'medium') return '#eab308' // Yellow
    return '#22c55e' // Green
  }

  return (
    <section className="feed-view-container" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Top Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Share2 size={22} color="#3b82f6" />
            {lang === 'ar' ? 'شبكة الانتشار ورصد التنسيق (CIB)' : 'Content Propagation & CIB Tracking'}
          </h2>
          <p style={{ color: 'var(--muted, #64748b)', fontSize: '0.875rem', marginTop: '0.25rem' }}>
            {lang === 'ar'
              ? 'تتبع مصدر المحتوى الأصلي (Patient Zero) وحركات إعادة النشر والتضخيم المنسقة عبر المنصات'
              : 'Trace Patient Zero origins and identify coordinated inauthentic behavior across networks'}
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button
            type="button"
            className="secondary-button"
            onClick={() => setFilterCibOnly(!filterCibOnly)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              background: filterCibOnly ? '#fee2e2' : undefined,
              borderColor: filterCibOnly ? '#ef4444' : undefined,
              color: filterCibOnly ? '#b91c1c' : undefined,
            }}
          >
            <Flame size={15} color={filterCibOnly ? '#ef4444' : undefined} />
            {lang === 'ar' ? 'حملات مشبوهة فقط (CIB)' : 'Coordinated Only'}
          </button>

          <button type="button" className="secondary-button" onClick={loadGraph} disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            {lang === 'ar' ? 'تحديث' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* KPI Stats Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
        <div className="stat-card" style={{ padding: '1rem', borderRadius: '12px', border: '1px solid var(--border, #e2e8f0)', background: 'var(--card, #fff)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--muted, #64748b)', fontSize: '0.8rem' }}>
            <span>{lang === 'ar' ? 'إجمالي العقد المرصودة' : 'Total Nodes'}</span>
            <Activity size={16} color="#3b82f6" />
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, marginTop: '0.4rem' }}>{summary?.total_nodes || 0}</div>
        </div>

        <div className="stat-card" style={{ padding: '1rem', borderRadius: '12px', border: '1px solid var(--border, #e2e8f0)', background: 'var(--card, #fff)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--muted, #64748b)', fontSize: '0.8rem' }}>
            <span>{lang === 'ar' ? 'المصادر الأصلية (Patient Zero)' : 'Patient Zero Origins'}</span>
            <Radio size={16} color="#8b5cf6" />
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, marginTop: '0.4rem', color: '#8b5cf6' }}>{summary?.patient_zero_count || 0}</div>
        </div>

        <div className="stat-card" style={{ padding: '1rem', borderRadius: '12px', border: '1px solid var(--border, #e2e8f0)', background: 'var(--card, #fff)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--muted, #64748b)', fontSize: '0.8rem' }}>
            <span>{lang === 'ar' ? 'روابط التضخيم والانتشار' : 'Amplification Paths'}</span>
            <GitFork size={16} color="#0284c7" />
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, marginTop: '0.4rem' }}>{summary?.total_edges || 0}</div>
        </div>

        <div className="stat-card" style={{ padding: '1rem', borderRadius: '12px', border: '1px solid var(--border, #e2e8f0)', background: summary?.cib_clusters_count ? '#fef2f2' : 'var(--card, #fff)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: summary?.cib_clusters_count ? '#b91c1c' : 'var(--muted, #64748b)', fontSize: '0.8rem' }}>
            <span>{lang === 'ar' ? 'تنسيق مشبوه محتمل (CIB)' : 'Suspicious CIB Clusters'}</span>
            <AlertTriangle size={16} color={summary?.cib_clusters_count ? '#ef4444' : '#64748b'} />
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 700, marginTop: '0.4rem', color: summary?.cib_clusters_count ? '#ef4444' : 'inherit' }}>
            {summary?.cib_clusters_count || 0}
          </div>
        </div>
      </div>

      {/* Main Graph Canvas & Inspector Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(300px, 1fr)', gap: '1.25rem', alignItems: 'start' }}>
        {/* Visual Graph Box */}
        <div style={{ background: 'var(--card, #fff)', border: '1px solid var(--border, #e2e8f0)', borderRadius: '12px', padding: '1.25rem', minHeight: '480px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, maxWidth: '320px' }}>
              <div className="search-box" style={{ width: '100%' }}>
                <Search size={15} />
                <input
                  type="text"
                  placeholder={lang === 'ar' ? 'بحث عن حساب أو كلمة...' : 'Search node/author...'}
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                  style={{ width: '100%', fontSize: '0.85rem' }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.75rem', color: 'var(--muted, #64748b)' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#8b5cf6' }} />
                {lang === 'ar' ? 'المصدر الأصلي' : 'Patient Zero'}
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#ef4444' }} />
                {lang === 'ar' ? 'حرج/خطير' : 'Critical/Dangerous'}
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#3b82f6' }} />
                {lang === 'ar' ? 'مضخم' : 'Amplifier'}
              </span>
            </div>
          </div>

          {/* Node Grid Visualization */}
          {loading ? (
            <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', color: 'var(--muted, #64748b)' }}>
              <RefreshCw size={24} className="animate-spin" />
            </div>
          ) : filteredNodes.length === 0 ? (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', color: 'var(--muted, #64748b)' }}>
              <Share2 size={36} strokeWidth={1.5} style={{ marginBottom: '0.5rem', opacity: 0.5 }} />
              <p>{lang === 'ar' ? 'لا توجد بيانات انتشار مطابقة' : 'No propagation nodes found'}</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', overflowY: 'auto', maxHeight: '520px', paddingRight: '0.25rem' }}>
              {/* Grouped by cluster */}
              {Array.from(new Set(filteredNodes.map(n => n.cluster_label || 'Direct'))).map(clusterLabel => {
                const clusterNodes = filteredNodes.filter(n => (n.cluster_label || 'Direct') === clusterLabel)
                return (
                  <div key={clusterLabel} style={{ border: '1px solid var(--border, #e2e8f0)', borderRadius: '10px', padding: '0.75rem', background: 'var(--background, #f8fafc)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
                      <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#64748b' }}>{clusterLabel}</span>
                      {clusterNodes.some(n => n.is_cib) && (
                        <span style={{ fontSize: '0.7rem', padding: '2px 6px', borderRadius: '6px', background: '#fee2e2', color: '#b91c1c', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '3px' }}>
                          <AlertTriangle size={12} />
                          CIB ALERT
                        </span>
                      )}
                    </div>

                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem', alignItems: 'center' }}>
                      {clusterNodes.map((node, i) => {
                        const isSelected = selectedNode?.id === node.id
                        const borderCol = node.is_patient_zero ? '#8b5cf6' : getSeverityColor(node.severity_level, node.is_dangerous)
                        return (
                          <div key={node.id} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            {i > 0 && <ArrowRight size={14} color="#94a3b8" style={{ transform: lang === 'ar' ? 'rotate(180deg)' : 'none' }} />}
                            <div
                              onClick={() => setSelectedNode(node)}
                              style={{
                                cursor: 'pointer',
                                padding: '0.5rem 0.75rem',
                                borderRadius: '8px',
                                background: isSelected ? 'var(--card, #fff)' : 'var(--card, #fff)',
                                border: `2px solid ${borderCol}`,
                                boxShadow: isSelected ? `0 0 0 3px ${borderCol}33` : '0 1px 2px rgba(0,0,0,0.05)',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '2px',
                                minWidth: '130px',
                              }}
                            >
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.75rem' }}>
                                <span style={{ fontWeight: 700 }}>{node.author}</span>
                                <span style={{ fontSize: '0.65rem', textTransform: 'uppercase', color: '#64748b' }}>{node.platform}</span>
                              </div>
                              <div style={{ fontSize: '0.7rem', color: '#64748b', display: 'flex', justifyContent: 'space-between' }}>
                                <span>{node.is_patient_zero ? '★ Patient Zero' : node.delay_from_origin}</span>
                                <span style={{ color: getSeverityColor(node.severity_level, node.is_dangerous), fontWeight: 700 }}>{node.severity_level}</span>
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Node Inspector Sidebar */}
        <div style={{ background: 'var(--card, #fff)', border: '1px solid var(--border, #e2e8f0)', borderRadius: '12px', padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <ShieldAlert size={18} color="#3b82f6" />
            {lang === 'ar' ? 'تفاصيل العقدة المرصودة' : 'Node Inspector'}
          </h3>

          {selectedNode ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.85rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                <span style={{ color: '#64748b' }}>{lang === 'ar' ? 'الحساب / الناشر:' : 'Author:'}</span>
                <span style={{ fontWeight: 700 }}>{selectedNode.author}</span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                <span style={{ color: '#64748b' }}>{lang === 'ar' ? 'المنصة:' : 'Platform:'}</span>
                <span style={{ textTransform: 'capitalize', fontWeight: 600 }}>{selectedNode.platform}</span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                <span style={{ color: '#64748b' }}>{lang === 'ar' ? 'الدور في السلسلة:' : 'Propagation Role:'}</span>
                <span style={{ fontWeight: 700, color: selectedNode.is_patient_zero ? '#8b5cf6' : '#0284c7' }}>
                  {selectedNode.is_patient_zero ? (lang === 'ar' ? 'المصدر الأول (Patient Zero)' : 'Patient Zero (Origin)') : lang === 'ar' ? `مضخم ثنائي (${selectedNode.delay_from_origin})` : `Secondary Amplifier (${selectedNode.delay_from_origin})`}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                <span style={{ color: '#64748b' }}>{lang === 'ar' ? 'درجة الخطورة:' : 'Severity:'}</span>
                <span style={{ fontWeight: 700, color: getSeverityColor(selectedNode.severity_level, selectedNode.is_dangerous) }}>
                  {selectedNode.severity_level.toUpperCase()}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                <span style={{ color: '#64748b' }}>{lang === 'ar' ? 'المشاعر:' : 'Sentiment:'}</span>
                <span style={{ fontWeight: 600 }}>{selectedNode.sentiment}</span>
              </div>

              <div>
                <span style={{ color: '#64748b', display: 'block', marginBottom: '0.3rem' }}>{lang === 'ar' ? 'نص المنشور:' : 'Post Content:'}</span>
                <div style={{ padding: '0.6rem', background: 'var(--background, #f8fafc)', borderRadius: '8px', border: '1px solid var(--border, #e2e8f0)', fontSize: '0.8rem', lineHeight: '1.4' }}>
                  {selectedNode.content_preview}
                </div>
              </div>

              {selectedNode.post_url && (
                <a
                  href={selectedNode.post_url}
                  target="_blank"
                  rel="noreferrer"
                  className="secondary-button"
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem', marginTop: '0.5rem', textDecoration: 'none' }}
                >
                  <ExternalLink size={14} />
                  {lang === 'ar' ? 'عرض الرابط الأصلي' : 'View Original Post'}
                </a>
              )}
            </div>
          ) : (
            <p style={{ color: '#64748b', fontSize: '0.85rem' }}>{lang === 'ar' ? 'حدد عقدة من الرسم لعرض تفاصيلها' : 'Select a node to inspect'}</p>
          )}

          {/* Top Amplifiers Section */}
          {summary?.top_amplifiers && summary.top_amplifiers.length > 0 && (
            <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border, #e2e8f0)' }}>
              <h4 style={{ fontSize: '0.85rem', fontWeight: 700, margin: '0 0 0.5rem 0', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <Users size={14} color="#3b82f6" />
                {lang === 'ar' ? 'أبرز القنوات المضخمة' : 'Top Amplifying Accounts'}
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                {summary.top_amplifiers.slice(0, 5).map(amp => (
                  <div key={amp.account} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#475569' }}>
                    <span style={{ fontWeight: 600 }}>{amp.account}</span>
                    <span style={{ background: '#e2e8f0', padding: '1px 6px', borderRadius: '4px', fontWeight: 700 }}>{amp.amplified_count}x</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

