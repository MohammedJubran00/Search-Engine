const LOGIN_URL = '/api/auth/login'
const ACCESS_TOKEN_KEY = 'ai-search-engine-access-token'
const REFRESH_TOKEN_KEY = 'ai-search-engine-refresh-token'
const CHAT_PATH = '/app.html'

const form = document.getElementById('login-form')
const submitBtn = document.getElementById('submit-btn')
const submitLabel = submitBtn.querySelector('.auth__submit-label')
const spinner = document.getElementById('submit-spinner')
const formError = document.getElementById('form-error')
const formSuccess = document.getElementById('form-success')
const togglePassword = document.getElementById('toggle-password')
const passwordInput = document.getElementById('password')

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function setBanner(element, messageHtml) {
  if (!messageHtml) {
    element.hidden = true
    element.replaceChildren()
    return
  }
  element.hidden = false
  element.replaceChildren()
  element.append(messageHtml)
}

function setTextBanner(element, message) {
  if (!message) {
    element.hidden = true
    element.textContent = ''
    return
  }
  element.hidden = false
  element.textContent = message
}

function setFieldError(fieldName, message) {
  const input = document.getElementById(fieldName)
  const error = document.getElementById(`${fieldName}-error`)
  if (!input || !error) return

  if (!message) {
    input.removeAttribute('aria-invalid')
    error.hidden = true
    error.textContent = ''
    return
  }

  input.setAttribute('aria-invalid', 'true')
  error.hidden = false
  error.textContent = message
}

function clearErrors() {
  setTextBanner(formError, '')
  setBanner(formSuccess, '')
  setFieldError('email', '')
  setFieldError('password', '')
}

function readErrorDetail(payload, fallback) {
  if (!payload || typeof payload !== 'object') return fallback

  if (typeof payload.error === 'string' && payload.error.trim()) {
    return payload.error.trim()
  }

  const detail = payload.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => item.msg || item.message || JSON.stringify(item))
      .join(' ')
  }
  if (typeof payload.message === 'string' && payload.message.trim()) {
    return payload.message
  }

  return fallback
}

function setLoading(isLoading) {
  submitBtn.disabled = isLoading
  spinner.hidden = !isLoading
  submitLabel.textContent = isLoading ? 'Logging in…' : 'Log in'
}

const signupParams = new URLSearchParams(window.location.search)
if (signupParams.get('signup') === 'success') {
  setTextBanner(formSuccess, 'Account created successfully. Please log in.')
}

togglePassword.addEventListener('click', () => {
  const show = passwordInput.type === 'password'
  passwordInput.type = show ? 'text' : 'password'
  togglePassword.textContent = show ? 'Hide' : 'Show'
  togglePassword.setAttribute('aria-pressed', show ? 'true' : 'false')
})

form.addEventListener('submit', async (event) => {
  event.preventDefault()
  clearErrors()

  const values = {
    email: form.email.value.trim().toLowerCase(),
    password: form.password.value,
  }

  if (!values.email) {
    setFieldError('email', 'Email is required.')
    return
  }
  if (!emailPattern.test(values.email)) {
    setFieldError('email', 'Enter a valid email address.')
    return
  }
  if (!values.password) {
    setFieldError('password', 'Password is required.')
    return
  }

  setLoading(true)

  let response
  try {
    response = await fetch(LOGIN_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(values),
    })
  } catch {
    setLoading(false)
    setTextBanner(
      formError,
      'Could not reach the API. Make sure FastAPI is running on port 8000.',
    )
    return
  }

  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  setLoading(false)

  if (response.status === 200 && payload?.access_token && payload?.refresh_token) {
    localStorage.setItem(ACCESS_TOKEN_KEY, payload.access_token)
    localStorage.setItem(REFRESH_TOKEN_KEY, payload.refresh_token)
    window.location.replace(CHAT_PATH)
    return
  }

  setTextBanner(
    formError,
    readErrorDetail(payload, 'Invalid email or password.'),
  )
})
