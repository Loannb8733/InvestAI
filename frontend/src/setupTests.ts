import '@testing-library/jest-dom'
import { configure } from '@testing-library/react'

// Les `findBy*` et `waitFor` abandonnent par défaut au bout de 1 s. Un
// `getByRole` coûte ~80 ms sur une page chargée comme les Paramètres : sur un
// runner CI une douzaine de fois plus lent, la marge disparaît et un test juste
// tombe au hasard, ce qui bloque le déploiement (550af5a). 4 s laissent la
// marge ; un vrai défaut échoue toujours, simplement plus tard — et avant le
// délai de test de Vitest, pour garder le message de Testing Library.
configure({ asyncUtilTimeout: 4000 })

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
