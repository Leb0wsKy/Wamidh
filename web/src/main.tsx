import 'leaflet/dist/leaflet.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ApiProvider } from './api/ApiProvider'
import App from './App'
import './i18n'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ApiProvider>
      <App />
    </ApiProvider>
  </StrictMode>,
)
