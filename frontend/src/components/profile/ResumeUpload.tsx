import { UploadCloud } from 'lucide-react'

interface ResumeUploadProps {
  onFileSelected?: (file: File) => void
}

/**
 * Drag-and-drop or file picker for resume upload (PDF / DOCX, max 10MB).
 * TODO(Phase 4): handle drag events, validation, and upload progress stages.
 */
export default function ResumeUpload({ onFileSelected }: ResumeUploadProps) {
  return (
    <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-card border border-dashed border-border-input bg-card px-6 py-10 text-center">
      <UploadCloud size={24} className="text-teal-deep" />
      <span className="text-[14px] font-medium text-text-primary">
        Drop your resume here
      </span>
      <span className="text-[12px] text-text-muted">
        PDF or DOCX, up to 10MB
      </span>
      <input
        type="file"
        accept=".pdf,.docx"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) onFileSelected?.(file)
        }}
      />
    </label>
  )
}
