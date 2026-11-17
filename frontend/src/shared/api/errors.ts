export function serverMessage(error: unknown): string | undefined {
  const detail = (error as { response?: { data?: { detail?: unknown } } } | undefined)?.response?.data?.detail
  return typeof detail === 'string' ? detail : undefined
}
