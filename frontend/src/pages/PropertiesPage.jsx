import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useApi } from '../lib/useApi'
import { currentMonth, formatAddress, money } from '../lib/format'
import AsyncState from '../components/AsyncState'
import Modal from '../components/Modal'
import PropertyForm from '../components/PropertyForm'
import StatusBadge from '../components/StatusBadge'

export default function PropertiesPage() {
  const [adding, setAdding] = useState(false)
  const navigate = useNavigate()
  // The dashboard summary already has each property with its current status and contacts
  const { data, error, loading, reload } = useApi(() => api.dashboard.summary(currentMonth()), [])
  const rows = data?.properties ?? []

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Properties</h1>
          <p className="page-subtitle">{data && `${rows.length} ${rows.length === 1 ? 'property' : 'properties'}`}</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
          + Add property
        </button>
      </div>

      <AsyncState loading={loading && !data} error={error} onRetry={reload}>
        {rows.length === 0 ? (
          <div className="empty">
            <p>You haven’t added any properties yet.</p>
            <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
              Add your first property
            </button>
          </div>
        ) : (
          <div className="grid-cards">
            {rows.map(({ property: p, primaryRenter, renterCount, status }) => (
              <Link key={p.id} to={`/properties/${p.id}`} className="card card-link">
                <div className="card-body">
                  <div className="section-header">
                    <h3>{p.name || p.street}</h3>
                    <StatusBadge status={status} />
                  </div>
                  <p className="muted">{formatAddress(p)}</p>
                  <p className="muted">
                    {money(p.monthlyRent)}/mo · {primaryRenter ? primaryRenter.name : 'No occupant'}
                    {renterCount > 1 && ` +${renterCount - 1}`}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </AsyncState>

      {adding && (
        <Modal title="Add property" onClose={() => setAdding(false)}>
          <PropertyForm
            onCancel={() => setAdding(false)}
            onSubmit={async (p) => {
              const created = await api.properties.create(p)
              navigate(`/properties/${created.id}`)
            }}
          />
        </Modal>
      )}
    </>
  )
}
