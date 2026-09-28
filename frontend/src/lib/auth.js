/*
 * Session storage for the JWT issued by the auth service.
 * The token is kept in localStorage so a page refresh keeps you signed in;
 * it expires on the server side after JWT_TTL_MINUTES (12 hours by default).
 */
const SESSION_KEY = 'rt:session'

export function getSession() {
  try {
    const s = JSON.parse(localStorage.getItem(SESSION_KEY))
    return s?.token && new Date(s.expiresAt) > new Date() ? s : null
  } catch {
    return null
  }
}

export const getToken = () => getSession()?.token

export function saveSession({ token, expiresAt, user }) {
  const session = { token, expiresAt, user }
  localStorage.setItem(SESSION_KEY, JSON.stringify(session))
  return session
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY)
}
