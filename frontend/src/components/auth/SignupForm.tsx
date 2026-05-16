import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../../lib/supabase'

export default function SignupForm() {
  const navigate = useNavigate()
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSignup = async () => {
    setLoading(true)
    setError('')
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { first_name: firstName, last_name: lastName }
      }
    })
    if (error) {
      setError(error.message)
      setLoading(false)
      return
    }
    navigate('/onboarding')
  }

  const inputStyle = {
    width: '100%',
    background: '#FAF9F7',
    border: '1px solid #D3D1C7',
    borderRadius: 8,
    padding: '9px 12px',
    fontSize: 13,
    boxSizing: 'border-box' as const
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div>
          <label style={{ fontSize: 12, fontWeight: 500, color: '#444441', display: 'block', marginBottom: 5 }}>First name</label>
          <input value={firstName} onChange={e => setFirstName(e.target.value)} placeholder="Aishwarya" style={inputStyle} />
        </div>
        <div>
          <label style={{ fontSize: 12, fontWeight: 500, color: '#444441', display: 'block', marginBottom: 5 }}>Last name</label>
          <input value={lastName} onChange={e => setLastName(e.target.value)} placeholder="Bhargava" style={inputStyle} />
        </div>
      </div>
      <div>
        <label style={{ fontSize: 12, fontWeight: 500, color: '#444441', display: 'block', marginBottom: 5 }}>Email</label>
        <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@email.com" style={inputStyle} />
      </div>
      <div>
        <label style={{ fontSize: 12, fontWeight: 500, color: '#444441', display: 'block', marginBottom: 5 }}>Password</label>
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" style={inputStyle} />
      </div>
      {error && <div style={{ fontSize: 12, color: '#D85A30' }}>{error}</div>}
      <button
        onClick={handleSignup}
        disabled={loading}
        style={{ width: '100%', background: '#D85A30', color: '#fff', border: 'none', borderRadius: 10, padding: 11, fontSize: 14, fontWeight: 500, cursor: 'pointer' }}
      >
        {loading ? 'Creating account...' : 'Create account'}
      </button>
    </div>
  )
}