import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, setUnauthorizedHandler } from '../lib/api'
import { clearSession, getSession, saveSession } from '../lib/auth'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => getSession()?.user ?? null)

  const logout = useCallback(() => {
    clearSession()
    setUser(null)
  }, [])

  // Any 401 from the API (expired or invalid token) returns the user to the sign-in page
  useEffect(() => setUnauthorizedHandler(logout), [logout])

  const value = {
    user,
    login: async (creds) => setUser(saveSession(await api.auth.login(creds)).user),
    register: async (details) => setUser(saveSession(await api.auth.register(details)).user),
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
