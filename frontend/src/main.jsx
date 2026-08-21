import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { isAuthenticated, redirectToLogin } from './api/auth'
import App from './App.jsx'
import './index.css'

if (!isAuthenticated()) {
  redirectToLogin()
} else {
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}
