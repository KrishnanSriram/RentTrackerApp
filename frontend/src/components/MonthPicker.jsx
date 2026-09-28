import { addMonths, monthLabel } from '../lib/format'

export default function MonthPicker({ value, onChange }) {
  return (
    <div className="row">
      <button type="button" className="btn btn-secondary btn-sm" onClick={() => onChange(addMonths(value, -1))} aria-label="Previous month">
        ←
      </button>
      <input
        type="month"
        className="input input-inline"
        value={value}
        onChange={(e) => e.target.value && onChange(e.target.value)}
        aria-label={monthLabel(value)}
      />
      <button type="button" className="btn btn-secondary btn-sm" onClick={() => onChange(addMonths(value, 1))} aria-label="Next month">
        →
      </button>
    </div>
  )
}
