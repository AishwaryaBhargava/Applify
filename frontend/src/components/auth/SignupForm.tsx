/**
 * Email + password signup form.
 * TODO(Phase 3): wire to authStore.signUp and surface validation errors.
 */
export default function SignupForm() {
  return (
    <form className="flex flex-col gap-3.5">
      <div className="grid grid-cols-2 gap-2.5">
        <div>
          <label className="mb-1.5 block text-[12px] font-medium text-text-primary">
            First name
          </label>
          <input
            className="w-full rounded-input border border-border-input bg-bg px-3 py-2.5 text-[13px] outline-none focus:border-teal-deep"
            placeholder="First"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-[12px] font-medium text-text-primary">
            Last name
          </label>
          <input
            className="w-full rounded-input border border-border-input bg-bg px-3 py-2.5 text-[13px] outline-none focus:border-teal-deep"
            placeholder="Last"
          />
        </div>
      </div>
      <div>
        <label className="mb-1.5 block text-[12px] font-medium text-text-primary">
          Email
        </label>
        <input
          type="email"
          placeholder="you@email.com"
          className="w-full rounded-input border border-border-input bg-bg px-3 py-2.5 text-[13px] outline-none focus:border-teal-deep"
        />
      </div>
      <div>
        <label className="mb-1.5 block text-[12px] font-medium text-text-primary">
          Password
        </label>
        <input
          type="password"
          placeholder="********"
          className="w-full rounded-input border border-border-input bg-bg px-3 py-2.5 text-[13px] outline-none focus:border-teal-deep"
        />
      </div>
      <button
        type="submit"
        className="mt-1 w-full rounded-btn bg-coral px-4 py-2.5 text-[14px] font-medium text-white"
      >
        Create account
      </button>
    </form>
  )
}
