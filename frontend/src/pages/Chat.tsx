import TopBar from '../components/common/TopBar'
import BackendStatus from '../components/common/BackendStatus'
import ChatThread from '../components/chat/ChatThread'
import ChatInput from '../components/chat/ChatInput'

/**
 * Active job chat page.
 * TODO(Phase 6): load the chat by id, run analysis, and stream responses.
 */
export default function Chat() {
  return (
    <div className="flex h-full flex-col">
      <TopBar
        title="Chat"
        subtitle="One workspace per job opening"
        actions={<BackendStatus />}
      />
      <ChatThread />
      <div className="px-6 py-4 text-[13px] text-text-secondary">
        Job chats arrive in Phase 6. Create a chat, paste a JD, and pick an
        analysis depth to get started.
      </div>
      <ChatInput disabled />
    </div>
  )
}
