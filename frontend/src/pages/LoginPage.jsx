import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { Field, FormError, useForm, useSubmit } from '../components/FormBits'

export default function LoginPage() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState('login')
  const [localError, setLocalError] = useState('')
  const { values, bind, setValues } = useForm({ name: '', email: '', password: '', confirm: '' })
  const isRegister = mode === 'register'

  const { run, saving, error } = useSubmit(async (v) => {
    if (isRegister) await register({ name: v.name, email: v.email, password: v.password })
    else await login({ email: v.email, password: v.password })
  })

  const submit = (e) => {
    setLocalError('')
    if (isRegister && values.password !== values.confirm) {
      e.preventDefault()
      setLocalError('Passwords do not match.')
      return
    }
    run(e, values)
  }

  const switchMode = () => {
    setMode(isRegister ? 'login' : 'register')
    setLocalError('')
    setValues((v) => ({ ...v, password: '', confirm: '' }))
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-title">
          <h1>Rent Tracker</h1>
          <p className="page-subtitle">{isRegister ? 'Create your account' : 'Sign in to your account'}</p>
        </div>

        <form className="form" onSubmit={submit}>
          <FormError message={localError || error} />
          {isRegister && (
            <Field label="Name">
              <input className="input" autoComplete="name" required {...bind('name')} />
            </Field>
          )}
          <Field label="Email">
            <input className="input" type="email" autoComplete="email" required {...bind('email')} />
          </Field>
          <Field label="Password" hint={isRegister ? 'At least 8 characters' : undefined}>
            <input
              className="input"
              type="password"
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              required
              minLength={isRegister ? 8 : undefined}
              maxLength={72}
              {...bind('password')}
            />
          </Field>
          {isRegister && (
            <Field label="Confirm password">
              <input className="input" type="password" autoComplete="new-password" required {...bind('confirm')} />
            </Field>
          )}
          <button type="submit" className="btn btn-primary btn-block" disabled={saving}>
            {saving ? 'Please wait…' : isRegister ? 'Create account' : 'Sign in'}
          </button>
        </form>

        <p className="auth-switch">
          {isRegister ? 'Already have an account? ' : 'New here? '}
          <button type="button" className="link" onClick={switchMode}>
            {isRegister ? 'Sign in' : 'Create an account'}
          </button>
        </p>
      </div>
    </div>
  )
}
