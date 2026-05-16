import { useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import SignupForm from '../components/auth/SignupForm'
import GoogleButton from '../components/auth/GoogleButton'
import Logo from '../components/common/Logo'
import styles from './Signup.module.css'

const features = [
  'Persistent profile powered by your resume',
  'AI fit analysis grounded in who you actually are',
  'Tailored resumes and cover letters on demand',
  'One chat per job, clean tracker, full pipeline view'
]

export default function Signup() {
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
          <h2>Apply smarter.<br /><span>Land the role</span> you deserve.</h2>
          <p>Applify gives every job application its own dedicated AI workspace. Paste a JD, get a fit analysis, generate a tailored resume.</p>
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
        <h1>Get started</h1>
        <p className={styles.subtitle}>Create your free Applify account</p>
        <SignupForm />
        <div className={styles.divider}>
          <div className={styles.dividerLine} />
          <span className={styles.dividerText}>or</span>
          <div className={styles.dividerLine} />
        </div>
        <GoogleButton label="Continue with Google" />
        <p className={styles.switchText}>
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  )
}