import { useEffect, useState } from 'react'
import { api, errMsg } from '../../api/client'
import type { LoadData } from '../../api/types'
import { ErrorBox, Spinner } from '../../components/ui'

const tone = (p: number) => (p >= 85 ? 'bg-rose-500' : p >= 60 ? 'bg-amber-500' : 'bg-emerald-500')

export default function LoadDashboard() {
  const [d, setD] = useState<LoadData | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const load = () => api<LoadData>('/load').then(setD).catch(e => setError(errMsg(e)))
    load()
    const t = setInterval(load, 60000)
    return () => clearInterval(t)
  }, [])
  if (!d) return error ? <ErrorBox message={error} /> : <Spinner />
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Загрузка оборудования на 7 дней</h1>
      <p className="text-sm text-slate-500">Горизонт планирования: {d.horizon_hours} ч (7 дней × 20 рабочих часов).</p>
      <div className="grid gap-4 md:grid-cols-2">
        {d.workshops.map(w => (
          <div key={w.workshop_id} className="card">
            <div className="mb-1 flex justify-between"><span className="font-semibold">{w.workshop}</span><span>{w.load_percent}%</span></div>
            <div className="h-3 rounded-full bg-slate-200 dark:bg-slate-800"><div className={`h-3 rounded-full ${tone(w.load_percent)}`} style={{ width: `${Math.min(100, w.load_percent)}%` }} /></div>
            <div className="mt-1 text-xs text-slate-500">Средняя загрузка активных принтеров</div>
          </div>
        ))}
      </div>
      <div className="card overflow-x-auto p-0">
        <table className="w-full">
          <thead className="border-b border-slate-200 dark:border-slate-800">
            <tr><th className="th">Принтер</th><th className="th">Цех</th><th className="th">Технология</th><th className="th">Статус</th><th className="th">Загрузка</th><th className="th">Занято, ч</th><th className="th">Простой, ч</th><th className="th">Задания</th></tr>
          </thead>
          <tbody>
            {d.printers.map(p => (
              <tr key={p.printer_id} className="border-b border-slate-100 dark:border-slate-800">
                <td className="td font-medium">{p.printer}</td><td className="td">{p.workshop}</td><td className="td">{p.technology}</td>
                <td className="td">{p.status === 'ACTIVE' ? 'Активен' : p.status === 'MAINTENANCE' ? 'На обслуживании' : 'Списан'}</td>
                <td className="td w-56">
                  <div className="h-2.5 rounded-full bg-slate-200 dark:bg-slate-800"><div className={`h-2.5 rounded-full ${tone(p.load_percent)}`} style={{ width: `${Math.min(100, p.load_percent)}%` }} /></div>
                  <span className="text-xs">{p.load_percent}%</span>
                </td>
                <td className="td">{p.planned_hours}</td><td className="td">{p.idle_hours}</td>
                <td className="td text-xs">{p.jobs.map(j => `${j.number} (${j.hours} ч)`).join(', ') || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
