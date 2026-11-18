import type { ReactElement } from 'react'
import { expect, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { createQueryClient } from '@/lib/queryClient'

export function renderWithQuery(element: ReactElement) {
  return render(<QueryClientProvider client={createQueryClient(false)}>{element}</QueryClientProvider>)
}

export async function settle(predicate: () => boolean) {
  await waitFor(() => expect(predicate()).toBe(true))
}

export function chooseOption(combobox: HTMLElement, name: string) {
  fireEvent.keyDown(combobox, { key: 'Enter' })
  fireEvent.keyDown(screen.getByRole('option', { name }), { key: 'Enter' })
}

export function reduceMotion() {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: query.includes('prefers-reduced-motion'),
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as MediaQueryList
  )
}
