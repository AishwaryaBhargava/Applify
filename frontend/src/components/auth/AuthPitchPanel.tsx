import Logo from '../common/Logo'

const FEATURES = [
  'Persistent profile from your resume',
  'AI fit analysis grounded in who you are',
  'Tailored resumes and cover letters',
  'One chat per job, full tracker',
]

/** Deep teal pitch panel shown beside the login and signup forms. */
export default function AuthPitchPanel() {
  return (
    <div className="hidden flex-col justify-between bg-teal-deep p-8 md:flex">
      <Logo size={32} variant="light" />

      <div className="py-6">
        <h2 className="font-serif text-[22px] font-medium leading-snug text-white">
          Your applications,
          <br />
          <span className="text-[#FAC775]">finally organized.</span>
        </h2>
        <p className="mb-5 mt-3 text-[13px] leading-relaxed text-teal-soft">
          One workspace for every job you apply to.
        </p>
        <ul className="flex flex-col gap-2.5">
          {FEATURES.map((feature) => (
            <li key={feature} className="flex items-start gap-2">
              <span className="mt-[7px] h-[5px] w-[5px] flex-shrink-0 rounded-full bg-amber" />
              <span className="text-[12px] leading-normal text-teal-soft">
                {feature}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <p className="text-[11px] text-teal-soft">
        Free during beta. No credit card required.
      </p>
    </div>
  )
}
