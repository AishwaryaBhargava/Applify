import GoogleIcon from '../../assets/icons/google.svg?react'
import { supabase } from '../../lib/supabase'

export default function GoogleButton({ label = 'Continue with Google' }: { label?: string }) {
  const handleGoogle = async () => {
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/chat`
      }
    })
  }

  return (
    <button
      onClick={handleGoogle}
      style={{
        width: '100%',
        background: '#fff',
        color: '#2C2C2A',
        border: '1px solid #D3D1C7',
        borderRadius: 10,
        padding: '11px',
        fontSize: 14,
        fontWeight: 500,
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 10,
        boxSizing: 'border-box'
      }}
    >
      <GoogleIcon width={18} height={18} />
      {label}
    </button>
  )
}