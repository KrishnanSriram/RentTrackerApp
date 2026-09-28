const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export const money = (n) => currency.format(Number(n) || 0)

/** 'YYYY-MM' for the current month. */
export function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export function todayISO() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 'YYYY-MM' -> 'September 2026' */
export function monthLabel(month) {
  const [y, m] = month.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

/** Shift a 'YYYY-MM' string by n months. */
export function addMonths(month, n) {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(y, m - 1 + n, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export function dateLabel(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function formatAddress(p) {
  const line1 = [p.street, p.unit && `Unit ${p.unit}`].filter(Boolean).join(', ')
  const line2 = [p.city, [p.state, p.zip].filter(Boolean).join(' ')].filter(Boolean).join(', ')
  return [line1, line2].filter(Boolean).join(', ')
}
