import { Field, FormActions, FormError, useForm, useSubmit } from './FormBits'

const BLANK = { name: '', street: '', unit: '', city: '', state: '', zip: '', monthlyRent: '' }

export default function PropertyForm({ initial, onSubmit, onCancel }) {
  const { values, bind } = useForm({ ...BLANK, ...initial })
  const { run, saving, error } = useSubmit(onSubmit)

  const submit = (e) =>
    run(e, {
      name: values.name,
      street: values.street,
      unit: values.unit,
      city: values.city,
      state: values.state,
      zip: values.zip,
      monthlyRent: Number(values.monthlyRent) || 0,
    })

  return (
    <form className="form" onSubmit={submit}>
      <FormError message={error} />
      <div className="form-grid">
        <Field label="Nickname (optional)" className="form-full" hint="e.g. “Maple St duplex”">
          <input className="input" {...bind('name')} />
        </Field>
        <Field label="Street address" className="form-full">
          <input className="input" required {...bind('street')} />
        </Field>
        <Field label="Unit / Apt">
          <input className="input" {...bind('unit')} />
        </Field>
        <Field label="City">
          <input className="input" required {...bind('city')} />
        </Field>
        <Field label="State">
          <input className="input" required minLength={2} maxLength={2} placeholder="OH" {...bind('state')} />
        </Field>
        <Field label="ZIP">
          <input className="input" required inputMode="numeric" pattern="\d{5}(-\d{4})?" {...bind('zip')} />
        </Field>
        <Field label="Monthly rent ($)" className="form-full">
          <input className="input" type="number" min="0" step="0.01" required {...bind('monthlyRent')} />
        </Field>
      </div>
      <FormActions onCancel={onCancel} saving={saving} submitLabel={initial?.id ? 'Save changes' : 'Add property'} />
    </form>
  )
}
