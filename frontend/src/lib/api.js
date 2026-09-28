/*
 * REST client for the Rent Tracker services.
 *
 * Every request goes to one base URL (the gateway). Locally that's the Vite dev
 * server, which proxies /api to http://localhost:8080 (see vite.config.js).
 * For a deployed build, set VITE_API_BASE_URL (e.g. https://api.example.com)
 * before `npm run build`.
 */
import { getToken } from './auth'

const BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

let onUnauthorized = () => {}
/** AuthContext registers a handler so an expired or invalid token signs the user out. */
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

/** FastAPI errors are either {detail: "text"} or {detail: [{loc, msg}, ...]} for validation. */
function errorMessage(body, status) {
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => {
        const field = d.loc?.filter((x) => x !== 'body').join('.')
        return field ? `${field}: ${d.msg}` : d.msg
      })
      .join('; ')
  }
  return status >= 500 ? 'The server had a problem. Please try again.' : `Request failed (${status})`
}

async function request(method, path, { body, params, auth = true } = {}) {
  const url = new URL(`${BASE}${path}`, window.location.origin)
  Object.entries(params || {}).forEach(([k, v]) => v != null && v !== '' && url.searchParams.set(k, v))

  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = getToken()
  if (auth && token) headers.Authorization = `Bearer ${token}`

  let res
  try {
    res = await fetch(url, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined })
  } catch {
    throw new ApiError('Cannot reach the server. Is the backend running?', 0)
  }

  const data = res.status === 204 ? null : await res.json().catch(() => null)
  if (!res.ok) {
    if (res.status === 401 && auth) onUnauthorized()
    throw new ApiError(errorMessage(data, res.status), res.status)
  }
  return data
}

const get = (path, params) => request('GET', path, { params })
const post = (path, body) => request('POST', path, { body })
const put = (path, body) => request('PUT', path, { body })
const del = (path, params) => request('DELETE', path, { params })

export const api = {
  auth: {
    register: (body) => request('POST', '/api/auth/register', { body, auth: false }),
    login: (body) => request('POST', '/api/auth/login', { body, auth: false }),
    me: () => get('/api/auth/me'),
  },
  properties: {
    list: () => get('/api/properties'),
    get: (id) => get(`/api/properties/${id}`),
    create: (body) => post('/api/properties', body),
    update: (id, body) => put(`/api/properties/${id}`, body),
    remove: (id) => del(`/api/properties/${id}`),
  },
  renters: {
    list: (propertyId) => get('/api/renters', { propertyId }),
    create: (body) => post('/api/renters', body),
    update: (id, body) => put(`/api/renters/${id}`, body),
    remove: (id) => del(`/api/renters/${id}`),
  },
  payments: {
    list: (filters) => get('/api/payments', filters), // { propertyId, month, fromMonth, toMonth }
    create: (body) => post('/api/payments', body),
    update: (id, body) => put(`/api/payments/${id}`, body),
    remove: (id) => del(`/api/payments/${id}`),
  },
  dashboard: {
    summary: (month) => get('/api/dashboard', { month }),
    history: (propertyId, months = 12, endMonth) =>
      get(`/api/dashboard/properties/${propertyId}/history`, { months, endMonth }),
  },
}
