import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

export function useAuth() {
  const { session, user, loading, initialize } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    initialize()
  }, [])

  const requireAuth = () => {
    if (!loading && !session) {
      navigate('/login')
    }
  }

  const requireNoAuth = () => {
    if (!loading && session) {
      navigate('/chat')
    }
  }

  return { session, user, loading, requireAuth, requireNoAuth }
}