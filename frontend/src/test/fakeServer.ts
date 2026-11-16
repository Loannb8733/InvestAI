import { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios'

export type Call = { method: string; url: string; params?: unknown; body?: unknown }
export type Reply = { status: number; data?: unknown }
export type Handler = (config: InternalAxiosRequestConfig) => Reply

export const ok =
  (data: unknown): Handler =>
  () => ({ status: 200, data })

export function createFakeServer() {
  const calls: Call[] = []
  const routes: Record<string, Handler> = {}

  const adapter: AxiosAdapter = async (config) => {
    const method = (config.method ?? 'get').toUpperCase()
    const url = config.url ?? ''
    const call: Call = { method, url }
    if (config.params && Object.keys(config.params).length > 0) call.params = config.params
    if (config.data !== undefined) call.body = JSON.parse(String(config.data))
    calls.push(call)
    const handler = routes[`${method} ${url}`]
    const reply = handler ? handler(config) : { status: 404, data: { detail: 'Not Found' } }
    const response = {
      data: reply.data ?? '',
      status: reply.status,
      statusText: String(reply.status),
      headers: new AxiosHeaders(),
      config,
    }
    if (reply.status >= 400) {
      throw new AxiosError(`Request failed with status code ${reply.status}`, 'ERR_BAD_RESPONSE', config, null, response)
    }
    return response
  }

  const reset = (defaults: Record<string, Handler>) => {
    calls.length = 0
    for (const key of Object.keys(routes)) delete routes[key]
    Object.assign(routes, defaults)
  }

  return { calls, routes, adapter, reset }
}

export function visibleText(): string[] {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  const lines: string[] = []
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent?.replace(/\s+/g, ' ').trim()
    if (text) lines.push(text)
  }
  return lines
}

export function polyfillRadixPointer() {
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.releasePointerCapture ??= () => {}
  Element.prototype.scrollIntoView ??= () => {}
}
