import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import PropertiesPage from './pages/PropertiesPage'
import PropertyDetailPage from './pages/PropertyDetailPage'
import BackupPage from './pages/BackupPage'

function AppRoutes() {
  const { user } = useAuth()

  if (!user) return <LoginPage />

  // key={user.id} resets every page's state when a different user signs in
  return (
    <Routes key={user.id}>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="properties" element={<PropertiesPage />} />
        <Route path="properties/:id" element={<PropertyDetailPage />} />
        <Route path="backup" element={<BackupPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

// HashRouter (URLs like /#/properties) works on plain S3 static hosting with no
// server-side rewrite rules, so page refreshes and deep links never 404.
export default function App() {
  return (
    <AuthProvider>
      <HashRouter>
        <AppRoutes />
      </HashRouter>
    </AuthProvider>
  )
}
