import { useState } from 'react'

/** Keeps a form's field values in one object. */
export function useForm(initial) {
  const [values, setValues] = useState(initial)
  const bind = (name) => ({
    name,
    value: values[name] ?? '',
    onChange: (e) => setValues((v) => ({ ...v, [name]: e.target.value })),
  })
  return { values, setValues, bind }
}

/**
 * Wraps an async submit handler: tracks "saving" and shows the API's error message.
 * `action` receives the form values and may throw; the error text is displayed.
 */
export function useSubmit(action) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const run = async (e, values) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await action(values)
    } catch (err) {
      setError(err.message || 'Something went wrong')
      setSaving(false)
    }
  }
  return { run, saving, error }
}

export function FormError({ message }) {
  return message ? <div className="form-error" role="alert">{message}</div> : null
}

export function Field({ label, hint, className = '', children }) {
  return (
    <label className={`field ${className}`}>
      <span className="label">{label}</span>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </label>
  )
}

export function FormActions({ onCancel, submitLabel = 'Save', saving = false }) {
  return (
    <div className="form-actions">
      <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={saving}>
        Cancel
      </button>
      <button type="submit" className="btn btn-primary" disabled={saving}>
        {saving ? 'Saving…' : submitLabel}
      </button>
    </div>
  )
}
