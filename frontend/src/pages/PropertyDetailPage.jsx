import { useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useApi } from '../lib/useApi'
import { currentMonth, dateLabel, formatAddress, money, monthLabel } from '../lib/format'
import AsyncState from '../components/AsyncState'
import Modal from '../components/Modal'
import PropertyForm from '../components/PropertyForm'
import OccupantForm from '../components/OccupantForm'
import PaymentForm from '../components/PaymentForm'
import StatusBadge from '../components/StatusBadge'
import MonthPicker from '../components/MonthPicker'

export default function PropertyDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [month, setMonth] = useState(currentMonth())
  const [modal, setModal] = useState(null) // { kind: 'property'|'occupant'|'payment', record? }
  const [actionError, setActionError] = useState('')

  const property = useApi(() => api.properties.get(id), [id])
  const renters = useApi(() => api.renters.list(id), [id])
  const payments = useApi(() => api.payments.list({ propertyId: id, month }), [id, month])
  const selected = useApi(() => api.dashboard.history(id, 1, month), [id, month]) // status for the chosen month
  const history = useApi(() => api.dashboard.history(id, 12), [id])

  if (property.error?.status === 404) return <Navigate to="/properties" replace />

  const close = () => setModal(null)
  const refreshRent = () => {
    payments.reload()
    selected.reload()
    history.reload()
  }
  // Delete buttons: confirm, call the API, refresh, and surface any error
  const act = async (question, fn, after) => {
    if (!confirm(question)) return
    setActionError('')
    try {
      await fn()
      after()
    } catch (err) {
      setActionError(err.message)
    }
  }

  const prop = property.data
  const people = renters.data ?? []
  const status = selected.data?.months[0]

  return (
    <AsyncState loading={!prop} error={property.error} onRetry={property.reload}>
      {prop && (
        <>
          <div className="page-header">
            <div>
              <Link to="/properties" className="link">
                ← Properties
              </Link>
              <h1>{prop.name || prop.street}</h1>
              <p className="page-subtitle">
                {formatAddress(prop)} · {money(prop.monthlyRent)}/month
              </p>
            </div>
            <div className="row">
              <button type="button" className="btn btn-secondary" onClick={() => setModal({ kind: 'property' })}>
                Edit property
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={() =>
                  act(
                    'Delete this property, its occupants and all payment history? This cannot be undone.',
                    () => api.properties.remove(id),
                    () => navigate('/properties'),
                  )
                }
              >
                Delete
              </button>
            </div>
          </div>

          {actionError && <div className="form-error">{actionError}</div>}

          {/* ---------- Occupants ---------- */}
          <section className="section">
            <div className="section-header">
              <h2>Occupants</h2>
              <button type="button" className="btn btn-primary btn-sm" onClick={() => setModal({ kind: 'occupant' })}>
                + Add occupant
              </button>
            </div>
            <AsyncState loading={renters.loading && !renters.data} error={renters.error} onRetry={renters.reload}>
              {people.length === 0 ? (
                <div className="empty">This property is vacant. Add an occupant to start tracking rent.</div>
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Email</th>
                        <th>Phone</th>
                        <th className="actions" />
                      </tr>
                    </thead>
                    <tbody>
                      {people.map((o) => (
                        <tr key={o.id}>
                          <td>{o.name}</td>
                          <td>
                            <span className={`badge badge-${o.role}`}>{o.role === 'primary' ? 'Primary' : 'Secondary'}</span>
                          </td>
                          <td>{o.email ? <a className="link" href={`mailto:${o.email}`}>{o.email}</a> : '—'}</td>
                          <td>{o.phone ? <a className="link" href={`tel:${o.phone}`}>{o.phone}</a> : '—'}</td>
                          <td className="actions">
                            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setModal({ kind: 'occupant', record: o })}>
                              Edit
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              onClick={() => act(`Remove ${o.name}?`, () => api.renters.remove(o.id), renters.reload)}
                            >
                              Remove
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </AsyncState>
          </section>

          {/* ---------- Payments for selected month ---------- */}
          <section className="section">
            <div className="section-header">
              <h2>Rent — {monthLabel(month)}</h2>
              <div className="row">
                <MonthPicker value={month} onChange={setMonth} />
                <button type="button" className="btn btn-primary btn-sm" onClick={() => setModal({ kind: 'payment' })}>
                  + Record payment
                </button>
              </div>
            </div>

            {status && (
              <div className="grid-stats">
                <div className="stat">
                  <span className="stat-label">Due</span>
                  <span className="stat-value">{money(status.due)}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Paid</span>
                  <span className="stat-value">{money(status.paid)}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Balance</span>
                  <span className="stat-value">{money(status.balance)}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Status</span>
                  <span className="stat-value">
                    <StatusBadge status={status.status} />
                  </span>
                </div>
              </div>
            )}

            <AsyncState loading={payments.loading && !payments.data} error={payments.error} onRetry={payments.reload}>
              {payments.data?.length === 0 ? (
                <div className="empty">No payments recorded for {monthLabel(month)}.</div>
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Date received</th>
                        <th>Method</th>
                        <th>Note</th>
                        <th className="num">Amount</th>
                        <th className="actions" />
                      </tr>
                    </thead>
                    <tbody>
                      {payments.data?.map((p) => (
                        <tr key={p.id}>
                          <td>{dateLabel(p.date)}</td>
                          <td>{p.method}</td>
                          <td>{p.note || '—'}</td>
                          <td className="num">{money(p.amount)}</td>
                          <td className="actions">
                            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setModal({ kind: 'payment', record: p })}>
                              Edit
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              onClick={() => act('Delete this payment?', () => api.payments.remove(p.id), refreshRent)}
                            >
                              Delete
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </AsyncState>
          </section>

          {/* ---------- 12-month history ---------- */}
          <section className="section">
            <h2>Last 12 months</h2>
            <AsyncState loading={history.loading && !history.data} error={history.error} onRetry={history.reload}>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Month</th>
                      <th className="num">Due</th>
                      <th className="num">Paid</th>
                      <th className="num">Balance</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.data?.months.map((h) => (
                      <tr key={h.month}>
                        <td>
                          <button type="button" className="link" onClick={() => setMonth(h.month)}>
                            {monthLabel(h.month)}
                          </button>
                        </td>
                        <td className="num">{money(h.due)}</td>
                        <td className="num">{money(h.paid)}</td>
                        <td className="num">{money(h.balance)}</td>
                        <td>
                          <StatusBadge status={h.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </AsyncState>
            <p className="hint">History uses the property’s current monthly rent for every month.</p>
          </section>

          {/* ---------- Modals ---------- */}
          {modal?.kind === 'property' && (
            <Modal title="Edit property" onClose={close}>
              <PropertyForm
                initial={prop}
                onCancel={close}
                onSubmit={async (p) => {
                  await api.properties.update(id, p)
                  close()
                  property.reload()
                  refreshRent()
                }}
              />
            </Modal>
          )}
          {modal?.kind === 'occupant' && (
            <Modal title={modal.record ? 'Edit occupant' : 'Add occupant'} onClose={close}>
              <OccupantForm
                initial={modal.record || { role: people.some((o) => o.role === 'primary') ? 'secondary' : 'primary' }}
                onCancel={close}
                onSubmit={async (o) => {
                  const body = { ...o, propertyId: id }
                  if (modal.record) await api.renters.update(modal.record.id, body)
                  else await api.renters.create(body)
                  close()
                  renters.reload()
                }}
              />
            </Modal>
          )}
          {modal?.kind === 'payment' && (
            <Modal title={modal.record ? 'Edit payment' : 'Record payment'} onClose={close}>
              <PaymentForm
                initial={modal.record}
                month={month}
                balance={status?.balance ?? prop.monthlyRent}
                onCancel={close}
                onSubmit={async (p) => {
                  const body = { ...p, propertyId: id }
                  if (modal.record) await api.payments.update(modal.record.id, body)
                  else await api.payments.create(body)
                  close()
                  refreshRent()
                }}
              />
            </Modal>
          )}
        </>
      )}
    </AsyncState>
  )
}
