import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './index.css'

// Crash forensics: a field crash ("the window closed itself") left NOTHING to
// read — no Windows event, no WebView dump, no log. Every uncaught error and
// rejected promise is beaconed to the backend, which appends it to app.log in
// the state dir. sendBeacon survives page teardown, which is exactly the
// moment worth recording. Rate-capped so an error loop cannot flood the disk.
let _logBudget = 50
const _beaconError = (kind, message, stack) => {
  if (_logBudget-- <= 0) return
  try {
    const body = JSON.stringify({
      kind,
      message: String(message || '').slice(0, 2000),
      stack: String(stack || '').slice(0, 4000),
      url: window.location.hash || '',
    })
    if (!navigator.sendBeacon('/api/client-log', new Blob([body], { type: 'application/json' }))) {
      fetch('/api/client-log', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }).catch(() => {})
    }
  } catch { /* logging must never throw */ }
}
window.addEventListener('error', (e) => {
  _beaconError('error', e.message, e.error && e.error.stack)
})
window.addEventListener('unhandledrejection', (e) => {
  const r = e.reason
  _beaconError('unhandledrejection', (r && r.message) || String(r), r && r.stack)
})

// Apply the saved theme before first paint to avoid a flash of default colors.
document.documentElement.dataset.theme = localStorage.getItem('mc-theme') ?? 'light'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
