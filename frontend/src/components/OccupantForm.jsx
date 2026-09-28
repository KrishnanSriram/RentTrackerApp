import { Field, FormActions, FormError, useForm, useSubmit } from './FormBits'

export default function OccupantForm({ initial, onSubmit, onCancel }) {
  const { values, bind } = useForm({ name: '', email: '', phone: '', role: 'primary', ...initial })
  const { run, saving, error } = useSubmit(onSubmit)

  const submit = (e) =>
    run(e, { name: values.name, email: values.email.trim(), phone: values.phone, role: values.role })

  return (
    <form className="form" onSubmit={submit}>
      <FormError message={error} />
      <div className="form-grid">
        <Field label="Full name" className="form-full">
          <input className="input" required {...bind('name')} />
        </Field>
        <Field label="Email">
          <input className="input" type="email" {...bind('email')} />
        </Field>
        <Field label="Phone">
          <input className="input" type="tel" placeholder="(614) 555-0123" {...bind('phone')} />
        </Field>
        <Field label="Contact type" className="form-full">
          <select className="input" {...bind('role')}>
            <option value="primary">Primary</option>
            <option value="secondary">Secondary</option>
          </select>
        </Field>
      </div>
      <FormActions onCancel={onCancel} saving={saving} submitLabel={initial?.id ? 'Save changes' : 'Add occupant'} />
    </form>
  )
}
