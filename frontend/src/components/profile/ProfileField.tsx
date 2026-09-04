interface ProfileFieldProps {
  label: string
  value?: string
  placeholder?: string
  onSave?: (value: string) => void
}

/**
 * Editable field within a profile section.
 * TODO(Phase 5): save on blur via PATCH /profile.
 */
export default function ProfileField({
  label,
  value = '',
  placeholder,
}: ProfileFieldProps) {
  return (
    <div className="mb-3">
      <label className="mb-1 block text-[11px] font-medium tracking-[0.6px] text-text-muted">
        {label.toUpperCase()}
      </label>
      <input
        defaultValue={value}
        placeholder={placeholder}
        className="w-full rounded-input border border-border bg-bg px-3 py-2 text-[13px] outline-none focus:border-teal-soft"
      />
    </div>
  )
}
