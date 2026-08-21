import { useEffect, useState } from 'react'
import { fetchCurrentUser, logout } from '../api/auth'
import './Header.css'

export default function Header() {
  const [user, setUser] = useState(null)
  const [isLoggingOut, setIsLoggingOut] = useState(false)

  useEffect(() => {
    let cancelled = false

    fetchCurrentUser()
      .then((profile) => {
        if (!cancelled) setUser(profile)
      })
      .catch(() => {
        // 401 already redirects. Keep Log out available without a name.
      })

    return () => {
      cancelled = true
    }
  }, [])

  async function handleLogout() {
    if (isLoggingOut) return
    setIsLoggingOut(true)
    await logout()
  }

  return (
    <header className="header">
      <div className="header__inner">
        <div className="header__brand">
          <span className="header__mark" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
              <circle cx="9.5" cy="9.5" r="6.25" stroke="currentColor" strokeWidth="1.7" />
              <path
                d="M14.2 14.2 19 19"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
              />
            </svg>
          </span>
          <div>
            <h1 className="header__title">AI Search Engine</h1>
            <p className="header__subtitle">
              Searches the web and uses AI to answer your questions.
            </p>
          </div>
        </div>

        <div className="header__actions">
          {user ? (
            <div className="header__identity">
              <p className="header__user-name">{user.full_name}</p>
              <p className="header__user-email">{user.email}</p>
            </div>
          ) : null}
          <button
            type="button"
            className="header__logout"
            onClick={handleLogout}
            disabled={isLoggingOut}
          >
            {isLoggingOut ? 'Logging out…' : 'Log out'}
          </button>
        </div>
      </div>
    </header>
  )
}
