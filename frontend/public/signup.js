const SIGNUP_URL = '/api/auth/signup'

const form = document.getElementById('signup-form')
const submitBtn = document.getElementById('submit-btn')
const submitLabel = submitBtn.querySelector('.auth__submit-label')
const spinner = document.getElementById('submit-spinner')
const formError = document.getElementById('form-error')
const formSuccess = document.getElementById('form-success')
const togglePassword = document.getElementById('toggle-password')
const passwordInput = document.getElementById('password')

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const specialChar = /[^A-Za-z0-9]/

function setBanner(element, message) {
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
  setBanner(formError, '')
  setBanner(formSuccess, '')
  setFieldError('full_name', '')
  setFieldError('email', '')
  setFieldError('password', '')
}

function validatePassword(password) {
  if (password.length < 8) {
    return 'Password must be at least 8 characters long.'
  }
  if (new TextEncoder().encode(password).length > 72) {
    return 'Password cannot be longer than 72 bytes.'
  }
  if (!/[A-Z]/.test(password)) {
    return 'Password must contain at least one uppercase letter.'
  }
  if (!/[a-z]/.test(password)) {
    return 'Password must contain at least one lowercase letter.'
  }
  if (!/\d/.test(password)) {
    return 'Password must contain at least one digit.'
  }
  if (!specialChar.test(password)) {
    return 'Password must contain at least one special character.'
  }
  return ''
}

function validateForm(values) {
  const errors = {}
  if (!values.full_name) {
    errors.full_name = 'Full name is required.'
  }
  if (!values.email) {
    errors.email = 'Email is required.'
  } else if (!emailPattern.test(values.email)) {
    errors.email = 'Enter a valid email address.'
  }
  const passwordError = validatePassword(values.password)
  if (passwordError) {
    errors.password = passwordError
  }
  return errors
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
  submitLabel.textContent = isLoading ? 'Creating account…' : 'Create account'
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
    full_name: form.full_name.value.trim(),
    email: form.email.value.trim().toLowerCase(),
    password: form.password.value,
  }

  const errors = validateForm(values)
  if (Object.keys(errors).length > 0) {
    for (const [field, message] of Object.entries(errors)) {
      setFieldError(field, message)
    }
    return
  }

  setLoading(true)

  let response
  try {
    response = await fetch(SIGNUP_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(values),
    })
  } catch {
    setLoading(false)
    setBanner(
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

  if (response.status === 201) {
    window.location.replace(window.AUTH_CONFIG.SIGNUP_SUCCESS_PATH)
    return
  }

  setBanner(
    formError,
    readErrorDetail(
      payload,
      response.status === 409
        ? 'An account with this email already exists.'
        : 'Could not create the account. Please try again.',
    ),
  )
})
