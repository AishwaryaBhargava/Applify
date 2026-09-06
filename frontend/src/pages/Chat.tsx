import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertCircle, MessageSquarePlus, Table2, User } from 'lucide-react'
import TopBar from '../components/common/TopBar'
import Badge from '../components/common/Badge'
import Spinner from '../components/common/Spinner'
import BackendStatus from '../components/common/BackendStatus'
import AnalysisCard from '../components/chat/AnalysisCard'
import AnalysisSkeleton from '../components/chat/AnalysisSkeleton'
import AnalysisTypeSelector from '../components/chat/AnalysisTypeSelector'
import ChatInput from '../components/chat/ChatInput'
import ChatThread from '../components/chat/ChatThread'
import KeywordMatchPanel from '../components/chat/KeywordMatchPanel'
import JobDescriptionPanel from '../components/chat/JobDescriptionPanel'
import OutputActions from '../components/chat/OutputActions'
import OutputsPanel from '../components/chat/OutputsPanel'
import NewChatButton from '../components/sidebar/NewChatButton'
import ResumeNudgeBanner from '../components/profile/ResumeNudgeBanner'
import useStream from '../hooks/useStream'
import { readDefaultAnalysisType } from '../lib/preferences'
import { NO_PROFILE_STATUS, useChatStore } from '../store/chatStore'
import { useUiStore } from '../store/uiStore'
import type { AnalysisType } from '../types'

const ANALYSIS_LABELS: Record<AnalysisType, string> = {
  quick: 'Quick snapshot',
  detailed: 'Detailed breakdown',
}

/** The landing state at /chat, before any chat is open. */
function ChatWelcome({ onMenu }: { onMenu: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <ResumeNudgeBanner />
      <TopBar
        title="Chat"
        subtitle="One workspace per job opening"
        actions={<BackendStatus />}
        onMenu={onMenu}
      />
      {/* This is the app's home: the place the sidebar logo, `/`, and a fresh
          sign-in all land. So it carries the primary action and a way on to
          the other two places worth being, rather than being a dead end. */}
      <div className="flex flex-1 items-center justify-center overflow-y-auto px-5 py-10 sm:px-6">
        <div className="max-w-md text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-btn bg-teal-light">
            <MessageSquarePlus size={22} className="text-teal-deep" />
          </div>
          <h2 className="font-serif text-2xl font-medium text-teal-ink">
            Start with a job description
          </h2>
          <p className="mx-auto mt-2 max-w-sm text-[13px] leading-relaxed text-text-secondary">
            Paste a posting and Applify scores your fit against your profile,
            then stays on the job — tailored resume, cover letter, answers.
          </p>
          <div className="mt-6 flex justify-center">
            <NewChatButton variant="inline" />
          </div>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-1 border-t border-border pt-5">
            <Link
              to="/profile"
              className="flex min-h-[40px] items-center gap-1.5 text-[13px] font-medium text-teal-deep underline-offset-2 hover:underline"
            >
              <User size={14} />
              Your profile
            </Link>
            <Link
              to="/tracker"
              className="flex min-h-[40px] items-center gap-1.5 text-[13px] font-medium text-teal-deep underline-offset-2 hover:underline"
            >
              <Table2 size={14} />
              Application tracker
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * The job chat page.
 *
 * `/chat` is the welcome state; `/chat/:id` rebuilds a chat entirely from
 * `GET /chats/{id}` — messages and the saved analysis both come from the
 * server, so a reload never re-runs a model call.
 */
export default function Chat() {
  const { id } = useParams<{ id: string }>()
  const toggleSidebar = useUiStore((state) => state.toggleSidebar)

  const activeChat = useChatStore((state) => state.activeChat)
  const messages = useChatStore((state) => state.messages)
  const analysis = useChatStore((state) => state.analysis)
  const keywordMatch = useChatStore((state) => state.keywordMatch)
  const outputs = useChatStore((state) => state.outputs)
  const isLoadingChat = useChatStore((state) => state.isLoadingChat)
  const isAnalyzing = useChatStore((state) => state.isAnalyzing)
  const error = useChatStore((state) => state.error)
  const analysisError = useChatStore((state) => state.analysisError)
  const analysisErrorStatus = useChatStore((state) => state.analysisErrorStatus)
  const isMatchingKeywords = useChatStore((state) => state.isMatchingKeywords)
  const keywordError = useChatStore((state) => state.keywordError)
  const keywordErrorStatus = useChatStore((state) => state.keywordErrorStatus)
  const loadChat = useChatStore((state) => state.loadChat)
  const runAnalysis = useChatStore((state) => state.runAnalysis)
  const runKeywordMatch = useChatStore((state) => state.runKeywordMatch)
  const generateOutput = useChatStore((state) => state.generateOutput)
  const reset = useChatStore((state) => state.reset)

  const { send, retry, abort, isStreaming, isConnecting } = useStream()

  // The depth chosen in Settings. Read on every render rather than held in
  // state: it is one localStorage lookup, and it means a change made in
  // another tab is reflected the next time this page draws.
  const preferredAnalysis = readDefaultAnalysisType()

  useEffect(() => {
    if (id) void loadChat(id)
    else reset()
  }, [id, loadChat, reset])

  // Leaving the page cancels any stream still running: its tokens have nowhere
  // left to land, and the backend has already stored what it produced.
  useEffect(() => () => reset(), [reset])

  if (!id) return <ChatWelcome onMenu={toggleSidebar} />

  if (isLoadingChat && !activeChat) {
    return (
      <div className="flex h-full flex-col">
        <TopBar title="Loading chat" onMenu={toggleSidebar} />
        <div className="flex flex-1 items-center justify-center">
          <Spinner size={22} className="text-teal-deep" />
        </div>
      </div>
    )
  }

  if (!activeChat) {
    return (
      <div className="flex h-full flex-col">
        <TopBar title="Chat" onMenu={toggleSidebar} />
        <div className="flex flex-1 items-center justify-center px-6">
          <div className="max-w-sm text-center">
            <p className="text-[14px] font-medium text-text-primary">
              {error ?? 'That job chat could not be opened.'}
            </p>
            <Link
              to="/chat"
              className="mt-3 inline-block text-[13px] font-medium text-teal-deep underline underline-offset-2"
            >
              Back to your chats
            </Link>
          </div>
        </div>
      </div>
    )
  }

  const needsResume = analysisErrorStatus === NO_PROFILE_STATUS

  const analysisArea = isAnalyzing ? (
    <AnalysisSkeleton />
  ) : analysis ? (
    <AnalysisCard
      analysis={analysis}
      title={activeChat.title}
      company={activeChat.company}
      onRerun={() => void runAnalysis(analysis.type, true)}
      isRerunning={isAnalyzing}
    />
  ) : (
    <div className="flex flex-col gap-3">
      <AnalysisTypeSelector
        onSelect={(type) => void runAnalysis(type)}
        disabled={isAnalyzing}
        preferred={preferredAnalysis}
      />

      {needsResume ? (
        <div className="flex items-start gap-2.5 rounded-box border border-amber/30 bg-amber-light px-3.5 py-3 text-[13px] leading-relaxed text-amber-ink">
          <AlertCircle size={15} className="mt-[2px] flex-shrink-0" />
          <div>
            <p className="font-medium">{analysisError}</p>
            <p className="mt-1">
              An analysis is only worth reading when it is grounded in your
              actual experience.{' '}
              <Link
                to="/onboarding"
                className="font-medium underline underline-offset-2"
              >
                Upload your resume
              </Link>
              , then run it again.
            </p>
          </div>
        </div>
      ) : (
        analysisError && (
          <div className="flex items-start gap-2.5 rounded-box bg-coral-light px-3.5 py-3 text-[13px] leading-relaxed text-coral-ink">
            <AlertCircle size={15} className="mt-[2px] flex-shrink-0" />
            <p>{analysisError}</p>
          </div>
        )
      )}
    </div>
  )

  const header = (
    <>
      <JobDescriptionPanel
        jdText={activeChat.jd_text ?? ''}
        // Once there is an analysis the card is what you came back to read.
        defaultOpen={!analysis}
      />
      <OutputsPanel
        outputs={outputs}
        chatId={activeChat.id}
        documentName={activeChat.company ?? activeChat.title}
      />
      {analysisArea}
      {/*
        Under the analysis rather than beside it: the fit score is the
        judgement the user came for, and the keyword match is what they act on
        once they have read it. A chat with no job description has nothing to
        extract keywords from, so the panel is not offered at all there.
      */}
      {activeChat.jd_text && (
        <KeywordMatchPanel
          match={keywordMatch}
          isRunning={isMatchingKeywords}
          onRun={(force) => void runKeywordMatch(force)}
          error={keywordError}
          needsResume={keywordErrorStatus === NO_PROFILE_STATUS}
        />
      )}
    </>
  )

  return (
    <div className="flex h-full flex-col">
      <ResumeNudgeBanner />
      <TopBar
        onMenu={toggleSidebar}
        title={
          <span className="flex items-center gap-2">
            <span className="truncate">{activeChat.title}</span>
            {activeChat.analysis_type && (
              <Badge tone="amber" className="flex-shrink-0">
                {ANALYSIS_LABELS[activeChat.analysis_type]}
              </Badge>
            )}
          </span>
        }
        subtitle={activeChat.company ?? 'No company on this chat'}
        actions={<BackendStatus />}
      />

      <ChatThread
        messages={messages}
        onRetry={() => void retry()}
        header={header}
        isConnecting={isConnecting}
        documentName={activeChat.company ?? activeChat.title}
        chatId={activeChat.id}
        outputs={outputs}
      />

      {/* Offered only once there is an analysis to ground the document in, and
          hidden while one is streaming so the chips cannot start a second. */}
      {analysis && !isStreaming && (
        <OutputActions
          onGenerate={(outputType, userContext) =>
            void generateOutput(outputType, userContext)
          }
          disabled={isAnalyzing}
        />
      )}

      <ChatInput
        onSend={(content) => void send(content)}
        onStop={abort}
        isStreaming={isStreaming}
      />
    </div>
  )
}
