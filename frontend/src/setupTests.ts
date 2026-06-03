import '@testing-library/jest-dom'

// jsdom does not implement ResizeObserver, which Radix UI primitives rely on
// (e.g. useSize). Provide a no-op polyfill so component tests can render.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? (ResizeObserverStub as unknown as typeof ResizeObserver)

// jsdom does not implement matchMedia, which the theme provider queries
// (prefers-color-scheme). Provide a stub that reports "no match".
if (!globalThis.matchMedia) {
  globalThis.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof globalThis.matchMedia
}
