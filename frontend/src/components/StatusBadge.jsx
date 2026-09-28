const LABELS = { paid: 'Paid', partial: 'Partial', unpaid: 'Unpaid', vacant: 'Vacant' }

export default function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{LABELS[status] || status}</span>
}
