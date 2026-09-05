import { create } from 'zustand'

/**
 * Chrome-level UI state that two unrelated components have to agree on.
 *
 * Today that is only the mobile sidebar: the hamburger lives in the page's top
 * bar and the drawer lives in the app shell, so neither can own the flag.
 * Deliberately not persisted — a drawer that is still open after a reload is a
 * bug, not a restored preference.
 */
export interface UiState {
  sidebarOpen: boolean
  openSidebar: () => void
  closeSidebar: () => void
  toggleSidebar: () => void
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: false,
  openSidebar: () => set({ sidebarOpen: true }),
  closeSidebar: () => set({ sidebarOpen: false }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
}))

export default useUiStore
