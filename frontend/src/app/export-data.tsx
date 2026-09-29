'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Check, Download, FileDown, Loader2 } from 'lucide-react'
import { apiUrl as buildApiUrl } from './api-client'

type Lang = 'ar' | 'en'
type Format = 'csv' | 'json' | 'xlsx' | 'pdf'

type Column = { key: string; label_ar: string; label_en: string; group: string; default: boolean }
type Options = {
  columns: Column[]
  default_columns: string[]
  ai_statuses: string[]
  formats: { value: Format; media_type: string }[]
  topics: { id: number; title: string }[]
  sources: { id: number; name: string; platform: string }[]
  limits: { max_rows: number; chunk_rows: number; pdf_max_detail_rows: number; default_range_days: number }
}
type Preview = {
  total_rows: number
  exported_rows: number
  truncated: boolean
  effective: {
    date_from: string
    date_to: string
    ai_status: string
    topic_id: number | null
    source_id: number | null
    search: string | null
    limit: number
    columns: string[]
  }
  by_ai_status: Record<string, number>
  by_severity: Record<string, number>
  by_platform: Record<string, number>
}
type Job = {
  job_id: string
  filename: string
  media_type: string
  /** Rows the file will actually contain; the progress bar's denominator. */
  total_rows: number
  /** Rows the filter matched, before the row cap was applied. */
  matched_rows: number
  truncated: boolean
  poll_url: string
  download_url: string
}
type Progress = { status: string; percent: number; rows_written: number; total_rows: number; error: string | null }

const AI_STATUS_LABEL: Record<Lang, Record<string, string>> = {
  ar: {
    all: 'كل الحالات',
    done: 'تم التحليل',
    pending: 'في الانتظار',
    processing: 'قيد التحليل',
    failed: 'فشل التحليل',
    skipped: 'تم التخطي',
  },
  en: { all: 'All statuses', done: 'Analyzed', pending: 'Pending', processing: 'Processing', failed: 'Failed', skipped: 'Skipped' },
}

const GROUP_LABEL: Record<Lang, Record<string, string>> = {
  ar: { identity: 'التعريف', content: 'المحتوى', ai: 'تحليل الذكاء الاصطناعي', flags: 'الوسوم والتنبيهات', dates: 'التواريخ والروابط' },
  en: { identity: 'Identity', content: 'Content', ai: 'AI analysis', flags: 'Tags & flags', dates: 'Dates & links' },
}

const GROUP_ORDER = ['identity', 'content', 'ai', 'flags', 'dates']

const FORMAT_LABEL: Record<Lang, Record<Format, string>> = {
  ar: { csv: 'CSV (Excel)', json: 'JSON', xlsx: 'Excel (xlsx)', pdf: 'تقرير PDF' },
  en: { csv: 'CSV (Excel)', json: 'JSON', xlsx: 'Excel (xlsx)', pdf: 'PDF report' },
}

const FORMAT_NOTE: Record<Lang, Record<Format, string>> = {
  ar: {
    csv: 'ملف نصي بترميز UTF-8 يفتح بالعربية مباشرة في Excel.',
    json: 'مستند JSON مع بيانات وصفية عن الفلاتر المستخدمة.',
    xlsx: 'مصنّف Excel بأعمدة ملوّنة وصفية قابلة للترشيح.',
    pdf: 'تقرير قابل للطباعة يتضمن ملخصاً إحصائياً وجدول تفاصيل.',
  },
  en: {
    csv: 'UTF-8 text file that opens directly in Excel with correct Arabic.',
    json: 'A JSON document carrying the applied filters as metadata.',
    xlsx: 'An Excel workbook with a styled header and an auto-filter.',
    pdf: 'A printable report with a statistical summary and a detail table.',
  },
}

const GROUP_FALLBACK: Record<Lang, string> = { ar: 'أخرى', en: 'Other' }

// How often the progress poll runs while the download body streams. The
// server writes a row batch every `chunk_rows`, so 450ms is frequent enough to
// look continuous without turning a slow connection into a request storm.
const POLL_INTERVAL_MS = 450

function apiUrl(path: string): string {
  return buildApiUrl(path)
}

async function readError(response: Response, lang: Lang): Promise<Error> {
  const fallback = lang === 'ar' ? 'تعذر إكمال الطلب.' : 'Unable to complete the request.'
  let detail = ''
  try {
    const body = await response.json()
    detail = typeof body?.detail === 'string' ? body.detail : ''
  } catch {
    // Non-JSON error body; the status-based message is enough.
  }
  return new Error(detail || `${fallback} (${response.status})`)
}

export function ExportDataPanel({ token, lang }: { token: string; lang: Lang }) {
  const [options, setOptions] = useState<Options | null>(null)
  const [columns, setColumns] = useState<string[]>([])
  const [format, setFormat] = useState<Format>('csv')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [aiStatus, setAiStatus] = useState('all')
  const [topicId, setTopicId] = useState('')
  const [sourceId, setSourceId] = useState('')
  const [search, setSearch] = useState('')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [job, setJob] = useState<Job | null>(null)
  const [progress, setProgress] = useState(0)
  const [rowsWritten, setRowsWritten] = useState(0)
  const [bytes, setBytes] = useState(0)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetch(apiUrl('/api/v1/export/options'), { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw await readError(response, lang)
        return response.json() as Promise<Options>
      })
      .then((body) => {
        if (cancelled) return
        setOptions(body)
        setColumns(body.default_columns)
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : (lang === 'ar' ? 'تعذر تحميل إعدادات التصدير.' : 'Unable to load the export catalogue.'))
      })
    return () => {
      cancelled = true
      stopPolling()
    }
  }, [token, lang, stopPolling])

  // `datetime-local` yields a wall-clock string with no offset. The column
  // stores naive UTC, so the value has to be converted to a real instant here
  // or the server would read local time as UTC and shift the window.
  const toIso = (value: string) => (value ? new Date(value).toISOString() : null)

  const payload = useCallback(() => ({
    date_from: toIso(dateFrom),
    date_to: toIso(dateTo),
    ai_status: aiStatus,
    topic_id: topicId ? Number(topicId) : null,
    source_id: sourceId ? Number(sourceId) : null,
    search: search.trim(),
    columns,
    format,
    lang,
  }), [dateFrom, dateTo, aiStatus, topicId, sourceId, search, columns, format, lang])

  const postJson = async <T,>(path: string, body: unknown): Promise<T> => {
    const response = await fetch(apiUrl(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
      cache: 'no-store',
    })
    if (!response.ok) throw await readError(response, lang)
    return response.json() as Promise<T>
  }

  const runPreview = async () => {
    if (previewing) return
    setPreviewing(true)
    setError('')
    setNotice('')
    setPreview(null)
    try {
      setPreview(await postJson<Preview>('/api/v1/export/preview', payload()))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === 'ar' ? 'تعذر حساب معاينة التصدير.' : 'Unable to compute the export preview.'))
    } finally {
      setPreviewing(false)
    }
  }

  const toggleColumn = (key: string) => {
    setColumns((current) => (current.includes(key) ? current.filter((entry) => entry !== key) : [...current, key]))
  }

  const startExport = async () => {
    if (job) return
    setError('')
    setNotice('')
    setPreview(null)
    setProgress(0)
    setRowsWritten(0)
    setBytes(0)
    try {
      const created = await postJson<Job>('/api/v1/export/jobs', payload())
      setJob(created)
      setNotice(
        created.truncated
          ? (lang === 'ar'
            ? `طابقت المرشحات ${created.matched_rows.toLocaleString()} صف؛ سيحتوي الملف على ${created.total_rows.toLocaleString()} صف.`
            : `${created.matched_rows.toLocaleString()} rows matched the filters; the file will contain ${created.total_rows.toLocaleString()} of them.`)
          : '',
      )

      // Poll while the body streams. The download and the poll are two
      // concurrent requests on purpose: the server only advances the counter
      // as bytes are produced, so the bar reflects real work rather than a
      // timer.
      const poll = setInterval(() => {
        fetch(apiUrl(created.poll_url), { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' })
          .then(async (response) => {
            if (!response.ok) throw await readError(response, lang)
            return response.json() as Promise<Progress>
          })
          .then((state) => {
            setProgress(state.percent)
            setRowsWritten(state.rows_written)
            if (state.error) setError(state.error)
          })
          .catch(() => {
            // A single failed poll is not fatal: the download is still going.
          })
      }, POLL_INTERVAL_MS)
      pollRef.current = poll

      const response = await fetch(apiUrl(created.download_url), {
        headers: { Authorization: `Bearer ${token}` },
        cache: 'no-store',
      })
      if (!response.ok) throw await readError(response, lang)
      const blob = await consumeBlob(response, setBytes)
      saveBlob(blob, created.filename)
      setProgress(100)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (lang === 'ar' ? 'تعذر تصدير البيانات.' : 'Unable to export the data.'))
    } finally {
      stopPolling()
      // Clearing the job re-enables the button so a second export can run; the
      // server-side job is single-use, so retrying needs a new one.
      setJob(null)
    }
  }

  const busy = previewing || job !== null
  const groupedColumns = GROUP_ORDER
    .map((group) => ({ group, items: (options?.columns ?? []).filter((column) => column.group === group) }))
    .filter((entry) => entry.items.length > 0)

  return (
    <div className="page-content export-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Data export</p>
          <h1>{lang === 'ar' ? 'تصدير البيانات' : 'Export data'}</h1>
          <p className="subhead">
            {lang === 'ar'
              ? 'صفِّ البيانات ثم نزّلها كملف. التصدير يُبثّ إلى المتصفح مباشرة دون تحميل كامل النتيجة في الذاكرة.'
              : 'Filter the archive, choose the columns, then download. Exports stream to the browser instead of buffering the whole result set.'}
          </p>
        </div>
      </div>
      {error && <div className="data-error"><AlertTriangle size={15} /> {error}</div>}
      {notice && <div className="export-notice">{notice}</div>}

      <div className="export-layout">
        <div className="panel export-filters">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Filters</p>
              <h2>{lang === 'ar' ? 'نطاق التصدير' : 'Export range'}</h2>
            </div>
          </div>
          <div className="export-date-row">
            <label>
              {lang === 'ar' ? 'من تاريخ' : 'From'}
              <input type="datetime-local" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
            </label>
            <label>
              {lang === 'ar' ? 'إلى تاريخ' : 'To'}
              <input type="datetime-local" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
            </label>
          </div>
          {!dateFrom && !dateTo && (
            <p className="field-help">
              {lang === 'ar'
                ? `بدون تاريخ، يُستخدم آخر ${options?.limits.default_range_days ?? 30} يوماً تلقائياً.`
                : `With no dates, the last ${options?.limits.default_range_days ?? 30} days are used automatically.`}
            </p>
          )}
          <div className="export-select-row">
            <label>
              {lang === 'ar' ? 'حالة تحليل الذكاء الاصطناعي' : 'AI status'}
              <select value={aiStatus} onChange={(event) => setAiStatus(event.target.value)}>
                {(options?.ai_statuses ?? ['all']).map((status) => (
                  <option value={status} key={status}>{AI_STATUS_LABEL[lang][status] ?? status}</option>
                ))}
              </select>
            </label>
            <label>
              {lang === 'ar' ? 'الموضوع' : 'Topic'}
              <select value={topicId} onChange={(event) => setTopicId(event.target.value)}>
                <option value="">{lang === 'ar' ? 'كل المواضيع' : 'All topics'}</option>
                {(options?.topics ?? []).map((topic) => (
                  <option value={String(topic.id)} key={topic.id}>{topic.title}</option>
                ))}
              </select>
            </label>
            <label>
              {lang === 'ar' ? 'المصدر' : 'Source'}
              <select value={sourceId} onChange={(event) => setSourceId(event.target.value)}>
                <option value="">{lang === 'ar' ? 'كل المصادر' : 'All sources'}</option>
                {(options?.sources ?? []).map((source) => (
                  <option value={String(source.id)} key={source.id}>{source.name} · {source.platform}</option>
                ))}
              </select>
            </label>
          </div>
          <label className="export-search">
            {lang === 'ar' ? 'بحث في النص والملخص' : 'Search text and summaries'}
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={lang === 'ar' ? 'كلمة أو عبارة' : 'A word or phrase'}
              maxLength={500}
            />
          </label>

          <div className="panel-heading">
            <div>
              <p className="eyebrow">Columns</p>
              <h2>{lang === 'ar' ? 'الأعمدة المُصدَّرة' : 'Exported columns'}</h2>
            </div>
            <span className="template-count">{columns.length}</span>
          </div>
          <div className="export-column-actions">
            <button type="button" onClick={() => setColumns(options?.default_columns ?? [])}>
              {lang === 'ar' ? 'الافتراضي' : 'Defaults'}
            </button>
            <button type="button" onClick={() => setColumns((options?.columns ?? []).map((column) => column.key))}>
              {lang === 'ar' ? 'تحديد الكل' : 'Select all'}
            </button>
            <button type="button" onClick={() => setColumns([])}>
              {lang === 'ar' ? 'إلغاء التحديد' : 'Clear'}
            </button>
          </div>
          {groupedColumns.map(({ group, items }) => (
            <fieldset className="export-column-group" key={group}>
              <legend>{GROUP_LABEL[lang][group] ?? GROUP_FALLBACK[lang]}</legend>
              <div className="export-column-grid">
                {items.map((column) => (
                  <label key={column.key}>
                    <input
                      type="checkbox"
                      checked={columns.includes(column.key)}
                      onChange={() => toggleColumn(column.key)}
                    />
                    <span>{lang === 'ar' ? column.label_ar : column.label_en}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          ))}

          <div className="panel-heading">
            <div>
              <p className="eyebrow">Format</p>
              <h2>{lang === 'ar' ? 'صيغة الملف' : 'File format'}</h2>
            </div>
          </div>
          <div className="export-format-grid">
            {(options?.formats ?? []).map((entry) => (
              <label className={format === entry.value ? 'selected' : ''} key={entry.value}>
                <input
                  type="radio"
                  name="export-format"
                  value={entry.value}
                  checked={format === entry.value}
                  onChange={() => setFormat(entry.value)}
                />
                <strong>{FORMAT_LABEL[lang][entry.value] ?? entry.value}</strong>
                <small>{FORMAT_NOTE[lang][entry.value]}</small>
              </label>
            ))}
          </div>

          <div className="export-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={busy || columns.length === 0}
              onClick={runPreview}
            >
              {previewing ? <span className="loading-spinner" /> : null}
              {lang === 'ar' ? 'معاينة العدد' : 'Preview count'}
            </button>
            <button
              type="button"
              className="primary-button"
              disabled={busy || columns.length === 0}
              onClick={startExport}
            >
              {job ? <Loader2 size={15} className="loading-spinner" /> : <Download size={15} />}
              {lang === 'ar' ? 'تصدير الآن' : 'Export now'}
            </button>
          </div>
        </div>

        <div className="export-side">
          {job && (
            <div className="panel export-progress-panel" role="status" aria-live="polite">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Exporting</p>
                  <h2>{lang === 'ar' ? 'جارٍ تجهيز الملف' : 'Preparing the file'}</h2>
                </div>
                <FileDown size={18} />
              </div>
              <div
                className="export-progress-track"
                role="progressbar"
                aria-valuenow={progress}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div className="export-progress-fill" style={{ width: `${progress}%` }} />
              </div>
              <p className="export-progress-caption">
                <strong>{progress}%</strong>
                {lang === 'ar'
                  ? ` — ${rowsWritten.toLocaleString()} من ${job.total_rows.toLocaleString()} صف`
                  : ` — ${rowsWritten.toLocaleString()} of ${job.total_rows.toLocaleString()} rows`}
                {bytes > 0 && (
                  <span className="export-progress-bytes">
                    {' · '}{(bytes / 1048576).toFixed(1)} MB
                  </span>
                )}
              </p>
              <p className="field-help">{job.filename}</p>
            </div>
          )}

          {preview && (
            <div className="panel export-preview">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Preview</p>
                  <h2>{lang === 'ar' ? 'معاينة النتائج' : 'Result preview'}</h2>
                </div>
                <Check size={18} />
              </div>
              <p className="export-preview-total">
                {preview.total_rows.toLocaleString()}
                <small>{lang === 'ar' ? ' سجل مطابق' : ' matching records'}</small>
              </p>
              {preview.truncated && (
                <p className="field-help">
                  {lang === 'ar'
                    ? `سيُصدَّر ${preview.exported_rows.toLocaleString()} صف فقط (الحد الأقصى ${options?.limits.max_rows.toLocaleString() ?? ''}).`
                    : `Only ${preview.exported_rows.toLocaleString()} rows will be exported (cap ${options?.limits.max_rows.toLocaleString() ?? ''}).`}
                </p>
              )}
              <Breakdown title={lang === 'ar' ? 'حسب حالة التحليل' : 'By AI status'} counts={preview.by_ai_status} lang={lang} />
              <Breakdown title={lang === 'ar' ? 'حسب مستوى الخطورة' : 'By severity'} counts={preview.by_severity} lang={lang} />
              <Breakdown title={lang === 'ar' ? 'حسب المنصة' : 'By platform'} counts={preview.by_platform} lang={lang} />
              <dl className="export-effective">
                <div>
                  <dt>{lang === 'ar' ? 'من' : 'From'}</dt>
                  <dd>{new Date(preview.effective.date_from).toLocaleString(lang === 'ar' ? 'ar-EG' : 'en-US')}</dd>
                </div>
                <div>
                  <dt>{lang === 'ar' ? 'إلى' : 'To'}</dt>
                  <dd>{new Date(preview.effective.date_to).toLocaleString(lang === 'ar' ? 'ar-EG' : 'en-US')}</dd>
                </div>
                <div>
                  <dt>{lang === 'ar' ? 'الأعمدة' : 'Columns'}</dt>
                  <dd>{preview.effective.columns.length}</dd>
                </div>
              </dl>
            </div>
          )}

          {!job && !preview && (
            <div className="panel placeholder-page">
              <h2>{lang === 'ar' ? 'جاهز للتصدير' : 'Ready to export'}</h2>
              <p>
                {lang === 'ar'
                  ? 'اختر الفلاتر والأعمدة، ثم عاين العدد قبل التنزيل.'
                  : 'Pick your filters and columns, then preview the count before downloading.'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Breakdown({ title, counts, lang }: { title: string; counts: Record<string, number>; lang: Lang }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1])
  if (entries.length === 0) return null
  const max = entries[0][1] || 1
  return (
    <div className="export-breakdown">
      <strong>{title}</strong>
      {entries.map(([key, count]) => (
        <div className="export-breakdown-row" key={key}>
          <span>{key === 'unknown' ? (lang === 'ar' ? 'غير محدد' : 'Unspecified') : key}</span>
          <i><b style={{ width: `${Math.round((count / max) * 100)}%` }} /></i>
          <em>{count.toLocaleString()}</em>
        </div>
      ))}
    </div>
  )
}

// Reads the body as a stream and hands the caller a running byte count so the
// panel can show transfer progress as well as row progress. A plain
// `response.blob()` would hide both the network progress and the fact that the
// server is still working.
async function consumeBlob(response: Response, onBytes: (total: number) => void): Promise<Blob> {
  const type = response.headers.get('content-type') ?? 'application/octet-stream'
  const reader = response.body?.getReader()
  if (!reader) {
    const blob = await response.blob()
    onBytes(blob.size)
    return blob
  }
  const parts: Uint8Array[] = []
  let received = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    if (value) {
      parts.push(value)
      received += value.length
      onBytes(received)
    }
  }
  return new Blob(parts as BlobPart[], { type })
}

function saveBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  // Revoking synchronously can cancel the download in some browsers; one turn
  // of the event loop is enough for the click to have been dispatched.
  window.setTimeout(() => window.URL.revokeObjectURL(url), 0)
}
