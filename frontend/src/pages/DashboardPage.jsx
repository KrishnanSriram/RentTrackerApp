import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useApi } from '../lib/useApi'
import { currentMonth, formatAddress, money, monthLabel } from '../lib/format'
import AsyncState from '../components/AsyncState'
import MonthPicker from '../components/MonthPicker'
import StatusBadge from '../components/StatusBadge'
import Modal from '../components/Modal'
import PaymentForm from '../components/PaymentForm'

export default function DashboardPage() {
  const [month, setMonth] = useState(currentMonth())
  const [paying, setPaying] = useState(null) // { property, balance }
  const { data, error, loading, reload } = useApi(() => api.dashboard.summary(month), [month])

  const totals = data?.totals
  const collectedPct = totals?.due ? Math.min(100, Math.round((totals.paid / totals.due) * 100)) : 0

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="page-subtitle">Rent collection for {monthLabel(month)}</p>
        </div>
        <MonthPicker value={month} onChange={setMonth} />
      </div>

      <AsyncState loading={loading && !data} error={error} onRetry={reload}>
        {data?.properties.length === 0 ? (
          <div className="empty">
            <p>No properties yet. Add your first property to start tracking rent.</p>
            <Link to="/properties" className="btn btn-primary">
              Add a property
            </Link>
          </div>
        ) : (
          data && (
            <>
              <div className="grid-stats">
                <div className="stat">
                  <span className="stat-label">Rent due</span>
                  <span className="stat-value">{money(totals.due)}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Collected</span>
                  <span className="stat-value">{money(totals.paid)}</span>
                  <div className="progress">
                    <div className="progress-bar" style={{ width: `${collectedPct}%` }} />
                  </div>
                </div>
                <div className="stat">
                  <span className="stat-label">Outstanding</span>
                  <span className="stat-value">{money(totals.outstanding)}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Paid in full</span>
                  <span className="stat-value">
                    {totals.paidInFull} / {totals.occupied}
                  </span>
                </div>
              </div>

              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Property</th>
                      <th>Primary contact</th>
                      <th className="num">Rent</th>
                      <th className="num">Paid</th>
                      <th className="num">Balance</th>
                      <th>Status</th>
                      <th className="actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {data.properties.map((r) => (
                      <tr key={r.property.id}>
                        <td>
                          <Link to={`/properties/${r.property.id}`} className="link">
                            {r.property.name || r.property.street}
                          </Link>
                          <div className="muted">{formatAddress(r.property)}</div>
                        </td>
                        <td>
                          {r.primaryRenter ? (
                            <>
                              <div>{r.primaryRenter.name}</div>
                              <div className="muted">{r.primaryRenter.phone || r.primaryRenter.email}</div>
                            </>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                        <td className="num">{money(r.due)}</td>
                        <td className="num">{money(r.paid)}</td>
                        <td className="num">{r.status === 'vacant' ? '—' : money(r.balance)}</td>
                        <td>
                          <StatusBadge status={r.status} />
                        </td>
                        <td className="actions">
                          {r.status !== 'vacant' && (
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => setPaying({ property: r.property, balance: r.balance })}
                            >
                              + Payment
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )
        )}
      </AsyncState>

      {paying && (
        <Modal title={`Record payment — ${paying.property.name || paying.property.street}`} onClose={() => setPaying(null)}>
          <PaymentForm
            month={month}
            balance={paying.balance}
            onCancel={() => setPaying(null)}
            onSubmit={async (p) => {
              await api.payments.create({ ...p, propertyId: paying.property.id })
              setPaying(null)
              reload()
            }}
          />
        </Modal>
      )}
    </>
  )
}
