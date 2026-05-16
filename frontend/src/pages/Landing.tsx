import { useEffect, useState } from 'react'
import api from '../services/api'

export default function Landing() {
  const [status, setStatus] = useState('')

  useEffect(() => {
    api.get('/health')
      .then(res => setStatus(res.data.status))
      .catch(() => setStatus('error'))
  }, [])

  return (
    <div style={{ padding: 40 }}>
      <h1>Applify</h1>
      <p>Backend status: {status || 'checking...'}</p>
    </div>
  )
}