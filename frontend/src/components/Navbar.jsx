import { NavLink } from 'react-router-dom'
import './Navbar.css'

const GITHUB_URL = 'https://github.com/ISHANPREET-1/pehredaar'

function Navbar() {
  return (
    <header className="navbar">
      <NavLink to="/" className="navbar-wordmark">
        Pehredaar
      </NavLink>
      <nav className="navbar-links">
        <NavLink to="/" end className={({ isActive }) => (isActive ? 'navbar-link is-active' : 'navbar-link')}>
          Home
        </NavLink>
        <NavLink to="/findings" className={({ isActive }) => (isActive ? 'navbar-link is-active' : 'navbar-link')}>
          Findings
        </NavLink>
        <NavLink to="/about" className={({ isActive }) => (isActive ? 'navbar-link is-active' : 'navbar-link')}>
          About
        </NavLink>
        <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="navbar-link navbar-github">
          GitHub
        </a>
      </nav>
    </header>
  )
}

export default Navbar
