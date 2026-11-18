import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, errMsg } from '../../api/client'
import type { Order, Recommendation } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import Chat from '../../components/Chat'
import ModelViewer from '../../components/ModelViewerLazy'
import { ParamsBlock, QuoteBlock } from '../../components/OrderSummary'
import StatusTimeline from '../../components/StatusTimeline'
import { ErrorBox, Field, Spinner, StatusBadge, VerdictPanel, fmtDate } from '../../components/ui'

export default function OrderReview() {
  const { id } = useParams()
  const { user } = useAuth()
  const [o, setO] = useState<Order | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [reason, setReason] = useState('')
  const [rec, setRec] = useState<Recommendation | null>(null)
  const [printer, setPrinter] = useState('')
  const [assignReason, setAssignReason] = useState('')
  const [adj, setAdj] = useState('')
  const [adjReason, setAdjReason] = useState('')

  const load = useCallback(() => api<Order>(`/orders/${id}`).then(setO).catch(e => setError(errMsg(e))), [id])
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t) }, [load])

  const canAssign = o && ['PAID', 'DISTRIBUTED'].includes(o.status)
  useEffect(() => {
    if (!canAssign) { setRec(null); return }
    api<Recommendation>(`/orders/${id}/recommendation`).then(r => { setRec(r); setPrinter(r.top[0]?.printer_id ?? '') }).catch(e => setError(errMsg(e)))
  }, [id, canAssign, o?.version])

  async function call(path: string, body: unknown, ok?: () => void) {
    setBusy(true); setError('')
    try { setO(await api<Order>(`/orders/${id}/${path}`, { method: 'POST', body })); ok?.() }
    catch (e) { setError(errMsg(e)) } finally { setBusy(false) }
  }
  const decide = (action: 'approve' | 'clarify' | 'reject') => call('decision', { action, reason }, () => setReason(''))

  if (!o) return error ? <ErrorBox message={error} /> : <Spinner />
  const cd = o.client_details
  const reviewable = ['MANUAL_REVIEW', 'CHECKED'].includes(o.status)
  const topIds = rec?.top.map(t => t.printer_id) ?? []
  const outsideTop = !!printer && !topIds.includes(printer)
  const transitions = o.available_transitions.filter(t => !(reviewable && t.to !== 'CANCELLED'))
  const canAdjust = user?.role === 'ADMIN' && ['MANUAL_REVIEW', 'CHECKED', 'CLARIFICATION'].includes(o.status)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">Заказ {o.number}</h1>
        <StatusBadge status={o.status} />
        <span className="text-sm text-slate-500">{cd?.full_name} · {cd?.email}{cd?.phone ? ' · ' + cd.phone : ''}{cd?.company_name ? ' · ' + cd.company_name : ''}</span>
      </div>
      <ErrorBox message={error} />
      <StatusTimeline order={o} />

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          {o.model && <ModelViewer orderId={o.id} version={o.model.version} format={o.model.format} height={380} />}
          <div className="card"><h2 className="mb-2 text-lg font-semibold">Проверка модели (E/W)</h2><VerdictPanel v={o.validation} /></div>
          <div className="card"><h2 className="mb-2 text-lg font-semibold">Параметры</h2><ParamsBlock order={o} /></div>
        </div>
        <div className="space-y-4">
          <div className="card"><h2 className="mb-2 text-lg font-semibold">Стоимость и срок</h2><QuoteBlock order={o} /></div>

          {reviewable && (
            <div className="card space-y-3">
              <h2 className="text-lg font-semibold">Решение менеджера</h2>
              <Field label="Причина / вопрос клиенту (обязательно для отказа и уточнения)">
                <textarea className="input" rows={3} value={reason} onChange={e => setReason(e.target.value)} />
              </Field>
              <div className="flex flex-wrap gap-2">
                <button className="btn-primary" disabled={busy} onClick={() => decide('approve')}>{o.status === 'MANUAL_REVIEW' ? 'Одобрить (признать выполнимым)' : 'Одобрить и отправить на оплату'}</button>
                <button className="btn-secondary" disabled={busy || !reason.trim()} onClick={() => decide('clarify')}>Запросить уточнение</button>
                <button className="btn-danger" disabled={busy || !reason.trim()} onClick={() => decide('reject')}>Отклонить</button>
              </div>
            </div>
          )}

          {canAdjust && (
            <div className="card space-y-3">
              <h2 className="text-lg font-semibold">Корректировка цены (администратор)</h2>
              <div className="grid grid-cols-3 gap-2">
                <Field label="Сумма, ₽ (− скидка)"><input className="input" type="number" value={adj} onChange={e => setAdj(e.target.value)} /></Field>
                <div className="col-span-2"><Field label="Причина"><input className="input" value={adjReason} onChange={e => setAdjReason(e.target.value)} /></Field></div>
              </div>
              <button className="btn-secondary" disabled={busy || adj === '' || !adjReason.trim()} onClick={() => call('adjustment', { adjustment: Number(adj), reason: adjReason }, () => { setAdj(''); setAdjReason('') })}>Применить корректировку</button>
            </div>
          )}

          {canAssign && rec && (
            <div className="card space-y-3">
              <h2 className="text-lg font-semibold">Назначение принтера</h2>
              {o.assignment && <p className="text-sm">Текущее назначение: <b>{o.assignment.printer}</b> ({o.assignment.workshop}), {fmtDate(o.assignment.planned_start)} — {fmtDate(o.assignment.planned_end)}</p>}
              <div className="space-y-1">
                <div className="text-sm font-medium">Рекомендации (топ-3)</div>
                {rec.top.length === 0 && <p className="text-sm text-rose-600">Подходящих принтеров нет.</p>}
                {rec.top.map((p, i) => (
                  <label key={p.printer_id} className="flex items-center gap-3 rounded-lg border border-slate-200 p-2 text-sm dark:border-slate-800">
                    <input type="radio" name="pr" checked={printer === p.printer_id} onChange={() => setPrinter(p.printer_id)} />
                    <span className="flex-1">{i + 1}. <b>{p.printer}</b> · {p.workshop}</span>
                    <span className="text-xs text-slate-500">оценка {p.score} · {fmtDate(p.planned_start)} → {fmtDate(p.planned_end)}</span>
                  </label>
                ))}
                {rec.others.length > 0 && (
                  <>
                    <div className="pt-1 text-sm font-medium">Другие подходящие (нужна причина)</div>
                    {rec.others.map(p => (
                      <label key={p.printer_id} className="flex items-center gap-3 rounded-lg border border-slate-200 p-2 text-sm dark:border-slate-800">
                        <input type="radio" name="pr" checked={printer === p.printer_id} onChange={() => setPrinter(p.printer_id)} />
                        <span className="flex-1">{p.printer} · {p.workshop}</span><span className="text-xs text-slate-500">оценка {p.score}</span>
                      </label>
                    ))}
                  </>
                )}
              </div>
              {outsideTop && <Field label="Причина выбора принтера вне топ-3"><input className="input" value={assignReason} onChange={e => setAssignReason(e.target.value)} /></Field>}
              <button className="btn-primary" disabled={busy || !printer || (outsideTop && !assignReason.trim())}
                onClick={() => call('assignment', { printer_id: printer, reason: assignReason }, () => setAssignReason(''))}>
                {o.status === 'PAID' ? 'Назначить и распределить' : 'Переназначить'}
              </button>
              {rec.excluded.length > 0 && (
                <details className="text-sm">
                  <summary className="cursor-pointer text-slate-500">Исключённые принтеры ({rec.excluded.length})</summary>
                  <ul className="mt-1 list-disc pl-5">{rec.excluded.map(e => <li key={e.printer_id}><b>{e.printer}</b>: {e.reason}</li>)}</ul>
                </details>
              )}
            </div>
          )}

          {transitions.length > 0 && (
            <div className="card space-y-3">
              <h2 className="text-lg font-semibold">Смена статуса</h2>
              <Field label="Причина (если требуется)"><input className="input" value={reason} onChange={e => setReason(e.target.value)} /></Field>
              <div className="flex flex-wrap gap-2">
                {transitions
                  .map(t => (
                    <button key={t.to} className={t.to === 'CANCELLED' ? 'btn-danger' : 'btn-secondary'}
                      disabled={busy || (t.reason_required && !reason.trim())}
                      onClick={() => call('status', { status: t.to, reason }, () => setReason(''))}>
                      → {t.label}{t.reason_required ? ' *' : ''}
                    </button>
                  ))}
              </div>
              <p className="text-xs text-slate-500">* требуется указать причину</p>
            </div>
          )}
        </div>
      </div>

      <Chat orderId={o.id} onChanged={load} />
      <div className="card">
        <h2 className="mb-2 text-lg font-semibold">История заказа</h2>
        <ul className="space-y-1 text-sm">
          {[...o.events].reverse().map(e => (
            <li key={e.id}><span className="text-slate-500">{fmtDate(e.created_at)}</span> — {e.actor}: {e.type === 'STATUS_CHANGED' ? `${e.from_status} → ${e.to_status}` : e.type}{e.reason ? ` (${e.reason})` : ''}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}
