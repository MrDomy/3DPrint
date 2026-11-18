import { describe, expect, it } from 'vitest'
import { STATUSES, rub } from './components/ui'

describe('ui helpers', () => {
  it('содержит 14 статусов', () => expect(STATUSES).toHaveLength(14))
  it('форматирует рубли', () => expect(rub(1748)).toContain('₽'))
})
