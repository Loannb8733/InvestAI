import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface PortfolioState {
  selectedPortfolioId: string | null
  setSelectedPortfolio: (id: string) => void
  clearSelectedPortfolio: () => void
}

export const usePortfolioStore = create<PortfolioState>()(
  persist(
    (set) => ({
      selectedPortfolioId: null,

      setSelectedPortfolio: (id: string) => {
        set({ selectedPortfolioId: id })
      },

      clearSelectedPortfolio: () => {
        set({ selectedPortfolioId: null })
      },
    }),
    {
      name: 'portfolio-storage',
      partialize: (state) => ({
        selectedPortfolioId: state.selectedPortfolioId,
      }),
    }
  )
)
