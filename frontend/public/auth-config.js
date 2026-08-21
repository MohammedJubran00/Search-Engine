/* Single source for auth storage keys and page paths.
 * Loaded as a classic script before login.js, signup.js, and the Chat app.
 */
window.AUTH_CONFIG = {
  ACCESS_TOKEN_KEY: 'ai-search-engine-access-token',
  REFRESH_TOKEN_KEY: 'ai-search-engine-refresh-token',
  LOGIN_PATH: '/login.html',
  SIGNUP_PATH: '/signup.html',
  CHAT_PATH: '/app.html',
  SIGNUP_SUCCESS_PATH: '/login.html?signup=success',
}
