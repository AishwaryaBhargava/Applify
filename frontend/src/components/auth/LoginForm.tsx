/**
 * Email + password login form.
 * TODO(Phase 3): wire to authStore.signIn and surface validation errors.
 */
export default function LoginForm() {
  return (
    <form className="flex flex-col gap-3.5">
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
        Sign in
      </button>
    </form>
  )
}
