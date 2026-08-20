import './Header.css'

export default function Header() {
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
      </div>
    </header>
  )
}
