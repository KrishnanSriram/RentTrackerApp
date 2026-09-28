import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const navClass = ({ isActive }) => `nav-link ${isActive ? 'nav-link-active' : ''}`

export default function Layout() {
  const { user, logout } = useAuth()

  return (
    <div className="app-shell">
      <header className="navbar">
        <div className="navbar-inner">
          <span className="navbar-brand">Rent Tracker</span>
          <nav className="navbar-links">
            <NavLink to="/" end className={navClass}>
              Dashboard
            </NavLink>
            <NavLink to="/properties" className={navClass}>
              Properties
            </NavLink>
            <NavLink to="/backup" className={navClass}>
              Import / export
            </NavLink>
          </nav>
          <div className="navbar-user">
            <span className="hidden sm:inline">{user.name || user.email}</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={logout}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </div>
  )
}
