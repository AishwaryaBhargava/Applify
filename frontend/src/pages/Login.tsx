import { useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import LoginForm from '../components/auth/LoginForm'
import GoogleButton from '../components/auth/GoogleButton'
import Logo from '../components/common/Logo'
import styles from './Login.module.css'

const features = [
  'Persistent profile powered by your resume',
  'AI fit analysis grounded in who you actually are',
  'Tailored resumes and cover letters on demand',
  'One chat per job, clean tracker, full pipeline view'
]

export default function Login() {
  const { session, loading, initialize } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    initialize()
  }, [])

  useEffect(() => {
    if (!loading && session) navigate('/chat')
  }, [session, loading])

  return (
    <div className={styles.page}>
      <div className={styles.left}>
        <div className={styles.logo}>
          <Logo variant="white" />
        </div>
        <div className={styles.pitch}>
          <h2>Your applications,<br /><span>finally organized.</span></h2>
          <p>One workspace for every job you apply to. Your profile, your analysis, your tracker — all in one place.</p>
          <div className={styles.features}>
            {features.map(f => (
              <div key={f} className={styles.featureItem}>
                <div className={styles.featureDot} />
                <span className={styles.featureText}>{f}</span>
              </div>
            ))}
          </div>
        </div>
        <div className={styles.leftFooter}>Free during beta. No credit card required.</div>
      </div>

      <div className={styles.right}>
        <h1>Welcome back</h1>
        <p className={styles.subtitle}>Sign in to your Applify account</p>
        <LoginForm />
        <div className={styles.divider}>
          <div className={styles.dividerLine} />
          <span className={styles.dividerText}>or</span>
          <div className={styles.dividerLine} />
        </div>
        <GoogleButton label="Continue with Google" />
        <p className={styles.switchText}>
          Don't have an account? <Link to="/signup">Sign up</Link>
        </p>
      </div>
    </div>
  )
}