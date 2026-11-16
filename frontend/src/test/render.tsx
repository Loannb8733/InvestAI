import type { ReactElement } from 'react'
import { expect } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

export function renderWithQuery(element: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{element}</QueryClientProvider>)
}

export async function settle(predicate: () => boolean) {
  await waitFor(() => expect(predicate()).toBe(true))
}

export function chooseOption(combobox: HTMLElement, name: string) {
  fireEvent.keyDown(combobox, { key: 'Enter' })
  fireEvent.keyDown(screen.getByRole('option', { name }), { key: 'Enter' })
}
