import { create } from 'zustand'

interface NotificationState {
  unreadCount: number
  setUnreadCount: (count: number) => void
  incrementUnread: () => void
  resetUnread: () => void
}

export const useNotificationStore = create<NotificationState>()(
  (set) => ({
    unreadCount: 0,

    setUnreadCount: (count: number) => {
      set({ unreadCount: count })
    },

    incrementUnread: () => {
      set((state) => ({ unreadCount: state.unreadCount + 1 }))
    },

    resetUnread: () => {
      set({ unreadCount: 0 })
    },
  })
)
