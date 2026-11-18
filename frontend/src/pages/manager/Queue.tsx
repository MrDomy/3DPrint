import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errMsg } from '../../api/client'
import type { OrderList } from '../../api/types'
import { ErrorBox, Spinner, StatusBadge, STATUSES, fmtDate, rub } from '../../components/ui'

interface Opt { id: string; name: string }

export default function Queue() {
  const nav = useNavigate()
  const [data, setData] = useState<OrderList | null>(null)
  const [error, setError] = useState('')
  const [materials, setMaterials] = useState<Opt[]>([])
  const [workshops, setWorkshops] = useState<Opt[]>([])
  const [f, setF] = useState({ status: '', priority: '', material: '', workshop: '', date_from: '', date_to: '', q: '' })
  const [page, setPage] = useState(1)

  useEffect(() => {
    api<Opt[]>('/catalog/materials').then(setMaterials).catch(() => {})
    api<Opt[]>('/workshops').then(setWorkshops).catch(() => {})
  }, [])
  useEffect(() => {
    const load = () => api<OrderList>('/orders', { params: { ...f, page } }).then(setData).catch(e => setError(errMsg(e)))
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [f, page])
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => { setPage(1); setF({ ...f, [k]: e.target.value }) }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Очередь заказов</h1>
      <div className="card grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <input className="input" placeholder="Поиск: номер, клиент" value={f.q} onChange={set('q')} />
        <select className="input" value={f.status} onChange={set('status')}>
          <option value="">Все статусы</option>
          {STATUSES.filter(s => s.code !== 'DRAFT').map(s => <option key={s.code} value={s.code}>{s.label}</option>)}
        </select>
        <select className="input" value={f.priority} onChange={set('priority')}>
          <option value="">Любой приоритет</option><option value="0">Обычный</option><option value="1">Высокий</option>
        </select>
        <select className="input" value={f.material} onChange={set('material')}>
          <option value="">Все материалы</option>{materials.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <select className="input" value={f.workshop} onChange={set('workshop')}>
          <option value="">Все цеха</option>{workshops.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
        <input className="input" type="date" title="Создан с" value={f.date_from} onChange={set('date_from')} />
        <input className="input" type="date" title="Создан по" value={f.date_to} onChange={set('date_to')} />
      </div>
      <ErrorBox message={error} />
      {!data ? <Spinner /> : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full">
            <thead className="border-b border-slate-200 dark:border-slate-800">
              <tr><th className="th">Номер</th><th className="th">Клиент</th><th className="th">Статус</th><th className="th">Технология / материал</th><th className="th">Кол-во</th><th className="th">Сумма</th><th className="th">Создан</th></tr>
            </thead>
            <tbody>
              {data.results.map(o => (
                <tr key={o.id} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50" onClick={() => nav(`/manager/orders/${o.id}`)}>
                  <td className="td font-medium">{o.number}</td>
                  <td className="td">{o.client.full_name}</td>
                  <td className="td"><StatusBadge status={o.status} /></td>
                  <td className="td">{o.technology?.code ?? '—'} / {o.material?.name ?? '—'}</td>
                  <td className="td">{o.quantity}</td>
                  <td className="td">{rub(o.total)}</td>
                  <td className="td">{fmtDate(o.created_at)}</td>
                </tr>
              ))}
              {data.results.length === 0 && <tr><td className="td text-center text-slate-500" colSpan={7}>Заказов не найдено.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {data && data.count > data.page_size && (
        <div className="flex items-center justify-center gap-3">
          <button className="btn-secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Назад</button>
          <span className="text-sm">Стр. {page} из {Math.ceil(data.count / data.page_size)}</span>
          <button className="btn-secondary" disabled={page * data.page_size >= data.count} onClick={() => setPage(page + 1)}>Вперёд</button>
        </div>
      )}
    </div>
  )
}
