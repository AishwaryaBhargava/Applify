import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../../lib/supabase'

export default function LoginForm() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async () => {
    setLoading(true)
    setError('')
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) {
      setError(error.message)
      setLoading(false)
      return
    }
    navigate('/chat')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <label style={{ fontSize: 12, fontWeight: 500, color: '#444441', display: 'block', marginBottom: 5 }}>Email</label>
        <input
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder="you@email.com"
          style={{ width: '100%', background: '#FAF9F7', border: '1px solid #D3D1C7', borderRadius: 8, padding: '9px 12px', fontSize: 13, boxSizing: 'border-box' }}
        />
      </div>
      <div>
        <label style={{ fontSize: 12, fontWeight: 500, color: '#444441', display: 'block', marginBottom: 5 }}>Password</label>
        <input
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          placeholder="••••••••"
          style={{ width: '100%', background: '#FAF9F7', border: '1px solid #D3D1C7', borderRadius: 8, padding: '9px 12px', fontSize: 13, boxSizing: 'border-box' }}
        />
      </div>
      <div style={{ textAlign: 'right', marginTop: -6 }}>
        <a href="#" style={{ fontSize: 12, color: '#0F6E56', textDecoration: 'none' }}>Forgot password?</a>
      </div>
      {error && <div style={{ fontSize: 12, color: '#D85A30' }}>{error}</div>}
      <button
        onClick={handleLogin}
        disabled={loading}
        style={{ width: '100%', background: '#D85A30', color: '#fff', border: 'none', borderRadius: 10, padding: 11, fontSize: 14, fontWeight: 500, cursor: 'pointer' }}
      >
        {loading ? 'Signing in...' : 'Sign in'}
      </button>
    </div>
  )
}