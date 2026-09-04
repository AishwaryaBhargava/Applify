import TopBar from '../components/common/TopBar'
import ProfileSection from '../components/profile/ProfileSection'

const SECTIONS = [
  'Experience',
  'Education',
  'Skills',
  'Certifications',
  'Projects',
  'Achievements',
]

/**
 * Full profile view and edit page.
 * TODO(Phase 5): fetch GET /profile and GET /profile/gaps, render real data.
 */
export default function Profile() {
  return (
    <div className="flex h-full flex-col">
      <TopBar title="Profile" subtitle="Everything the AI knows about you" />
      <div className="flex-1 overflow-y-auto px-6 py-6 md:px-8">
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {SECTIONS.map((section) => (
            <ProfileSection
              key={section}
              title={section}
              description="Populated after your resume is parsed."
            />
          ))}
        </div>
      </div>
    </div>
  )
}
