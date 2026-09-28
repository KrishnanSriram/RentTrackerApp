import { useRef, useState } from 'react'
import { api } from '../lib/api'
import { todayISO } from '../lib/format'

const PROPERTY_FIELDS = ['name', 'street', 'unit', 'city', 'state', 'zip', 'monthlyRent']
const pick = (obj, keys) => Object.fromEntries(keys.map((k) => [k, obj[k] ?? '']))

export default function BackupPage() {
  const fileRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const download = async () => {
    setBusy(true)
    setError('')
    try {
      const [properties, renters, payments] = await Promise.all([
        api.properties.list(),
        api.renters.list(),
        api.payments.list(),
      ])
      const blob = new Blob([JSON.stringify({ properties, renters, payments }, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `rent-tracker-export-${todayISO()}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  /** Adds everything in the file as new records. Works with this page's export and with
   *  backups from the earlier browser-only version (which called renters "occupants"). */
  const upload = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setMessage('')
    setError('')
    let backup
    try {
      backup = JSON.parse(await file.text())
      if (!Array.isArray(backup.properties)) throw new Error()
    } catch {
      setError('That file is not a valid Rent Tracker backup.')
      return
    }
    const renters = backup.renters || backup.occupants || []
    const payments = backup.payments || []
    if (!confirm(`Import ${backup.properties.length} properties, ${renters.length} renters and ${payments.length} payments? They are added alongside your existing data.`)) return

    setBusy(true)
    const idMap = {} // old property id -> new property id
    try {
      for (const p of backup.properties) {
        const created = await api.properties.create({ ...pick(p, PROPERTY_FIELDS), monthlyRent: Number(p.monthlyRent) || 0 })
        idMap[p.id] = created.id
      }
      for (const r of renters) {
        if (!idMap[r.propertyId]) continue
        await api.renters.create({ ...pick(r, ['name', 'email', 'phone', 'role']), propertyId: idMap[r.propertyId] })
      }
      for (const p of payments) {
        if (!idMap[p.propertyId]) continue
        await api.payments.create({
          ...pick(p, ['month', 'date', 'method', 'note']),
          amount: Number(p.amount),
          propertyId: idMap[p.propertyId],
        })
      }
      setMessage('Import complete.')
    } catch (err) {
      setError(`Import stopped part-way: ${err.message}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Import / export</h1>
          <p className="page-subtitle">Download all your data as a JSON file, or import a file from an earlier export.</p>
        </div>
      </div>
      <div className="card">
        <div className="card-body">
          <div className="row">
            <button type="button" className="btn btn-primary" onClick={download} disabled={busy}>
              Export data
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => fileRef.current.click()} disabled={busy}>
              Import from file…
            </button>
            <input ref={fileRef} type="file" accept="application/json" hidden onChange={upload} />
          </div>
          {busy && <p className="muted">Working…</p>}
          {message && <p className="muted">{message}</p>}
          {error && <div className="form-error">{error}</div>}
        </div>
      </div>
    </>
  )
}
