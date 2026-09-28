import { money, todayISO } from '../lib/format'
import { Field, FormActions, FormError, useForm, useSubmit } from './FormBits'

const METHODS = ['Check', 'Cash', 'Bank transfer', 'Zelle', 'Venmo', 'Other']

/**
 * Records one payment toward a month's rent. A month can have any number of
 * payments; the status is computed server-side from their total.
 * `balance` is the amount still owed for that month (used to pre-fill).
 */
export default function PaymentForm({ initial, month, balance, onSubmit, onCancel }) {
  const { values, bind, setValues } = useForm({
    month,
    amount: balance > 0 ? balance : '',
    date: todayISO(),
    method: 'Check',
    note: '',
    ...initial,
  })
  const { run, saving, error } = useSubmit(onSubmit)
  const isNew = !initial?.id

  const submit = (e) =>
    run(e, {
      month: values.month,
      amount: Number(values.amount),
      date: values.date,
      method: values.method,
      note: values.note,
    })

  return (
    <form className="form" onSubmit={submit}>
      <FormError message={error} />
      <div className="form-grid">
        <Field label="Rent month">
          <input className="input" type="month" required {...bind('month')} />
        </Field>
        <Field label="Date received">
          <input className="input" type="date" required {...bind('date')} />
        </Field>
        <Field
          label="Amount ($)"
          hint={isNew && balance > 0 ? `Balance due this month: ${money(balance)}. Enter less for a partial payment.` : undefined}
        >
          <input className="input" type="number" min="0.01" step="0.01" required {...bind('amount')} />
        </Field>
        <Field label="Method">
          <select className="input" {...bind('method')}>
            {METHODS.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
        </Field>
        <Field label="Note" className="form-full">
          <input className="input" placeholder="e.g. check #1042" {...bind('note')} />
        </Field>
      </div>
      {isNew && balance > 0 && (
        <div className="row">
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setValues((v) => ({ ...v, amount: balance }))}>
            Full balance
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setValues((v) => ({ ...v, amount: Math.round((balance / 2) * 100) / 100 }))}>
            Half
          </button>
        </div>
      )}
      <FormActions onCancel={onCancel} saving={saving} submitLabel={isNew ? 'Record payment' : 'Save changes'} />
    </form>
  )
}
