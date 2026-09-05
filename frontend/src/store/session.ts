import { useAuthStore } from './authStore'
import { useChatListStore } from './chatListStore'
import { useChatStore } from './chatStore'
import { useProfileStore } from './profileStore'
import { useTrackerStore } from './trackerStore'

/**
 * Ends the session and drops everything persisted for this user.
 *
 * Signing out has to clear the chat list, the tracker and the profile as well
 * as the Supabase session: all three are persisted to localStorage, so without
 * this the next person to sign in on the machine would see the previous user's
 * applications flash on screen before the first fetch replaced them.
 */
export async function endSession(): Promise<void> {
  await useAuthStore.getState().signOut()
  useChatStore.getState().reset()
  useProfileStore.getState().reset()
  useChatListStore.getState().reset()
  useTrackerStore.getState().reset()
}
