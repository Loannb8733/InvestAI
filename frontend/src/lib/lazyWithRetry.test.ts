import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { lazyWithRetry } from './lazyWithRetry'

/**
 * Le rattrapage des chunks périmés après un déploiement.
 *
 * Les pages sont chargées à la demande. Après une mise en ligne, les fichiers
 * changent de nom : un onglet resté ouvert garde des références vers des
 * chunks qui n'existent plus, et la page s'ouvre… sur rien.
 *
 * Ce module recharge alors la page **une fois**, puis laisse l'erreur remonter.
 * Les deux moitiés comptent autant : sans le rechargement, l'utilisateur voit
 * une page blanche ; sans la limite, il tombe dans une boucle de rechargements
 * qui ne montre jamais l'erreur.
 *
 * Le module était couvert à 42 % — la moitié qui compte, celle du repli, ne
 * l'était pas.
 */

const rechargements = vi.hoisted(() => ({ nombre: 0 }))

beforeEach(() => {
  rechargements.nombre = 0
  sessionStorage.clear()
  vi.useFakeTimers()
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { reload: () => { rechargements.nombre += 1 } },
  })
})

afterEach(() => {
  vi.useRealTimers()
})

/** Déclenche le chargement du composant paresseux et rend sa promesse. */
function charger(composant: ReturnType<typeof lazyWithRetry>) {
  // React.lazy garde sa fabrique dans `_payload._result` une fois amorcée.
  const charge = (composant as unknown as { _payload: { _result: () => Promise<unknown> } })._payload
  return (charge._result as () => Promise<unknown>)()
}

describe('chargement normal', () => {
  it('rend le module quand il se charge', async () => {
    const module = { default: () => null }

    const composant = lazyWithRetry(async () => module)

    await expect(charger(composant)).resolves.toBe(module)
    expect(rechargements.nombre).toBe(0)
  })
})

describe('chunk introuvable', () => {
  it('recharge la page à la première défaillance', async () => {
    const composant = lazyWithRetry(() => Promise.reject(new Error('Failed to fetch dynamically imported module')))

    const promesse = charger(composant)
    await vi.advanceTimersByTimeAsync(0)

    expect(rechargements.nombre).toBe(1)
    /* La promesse ne se dénoue **ni dans un sens ni dans l'autre** : la page
       se recharge, et React ne doit pas afficher son écran d'erreur pendant ce
       temps.

       Surveiller le seul `then` ne prouvait rien — il ne se déclenche pas plus
       sur un rejet que sur une promesse en suspens, et le canari qui relançait
       l'erreur restait muet. */
    let issue: 'aucune' | 'resolue' | 'rejetee' = 'aucune'
    void promesse.then(
      () => { issue = 'resolue' },
      () => { issue = 'rejetee' },
    )
    await vi.advanceTimersByTimeAsync(100)
    expect(issue).toBe('aucune')
  })

  it("laisse l'erreur remonter à la seconde défaillance", async () => {
    /* Le rechargement n'a pas suffi : le problème n'est pas un chunk périmé.
       Insister ferait boucler l'onglet sans jamais rien montrer. */
    const echec = () => Promise.reject(new Error('Failed to fetch dynamically imported module'))
    const composant = lazyWithRetry(echec)

    void charger(composant)
    await vi.advanceTimersByTimeAsync(0)
    const seconde = charger(composant).catch((e) => e)

    await expect(seconde).resolves.toBeInstanceOf(Error)
    expect(rechargements.nombre).toBe(1)
  })

  it('oublie la tentative après trente secondes', async () => {
    /* Sans cette purge, un onglet resté ouvert longtemps ne se rattraperait
       plus jamais : la première défaillance de la session condamnerait tous
       les déploiements suivants. */
    const echec = () => Promise.reject(new Error('Failed to fetch dynamically imported module'))
    const composant = lazyWithRetry(echec)

    void charger(composant)
    await vi.advanceTimersByTimeAsync(0)
    expect(sessionStorage.length).toBeGreaterThan(0)

    await vi.advanceTimersByTimeAsync(30001)

    expect(sessionStorage.length).toBe(0)
  })

  it('compte les modules séparément', async () => {
    /* Deux pages périmées valent deux rattrapages : une clé par chemin
       d'import. Une clé unique ferait échouer la seconde page pour avoir
       simplement suivi la première.

       La clé est tirée du **texte** de la fabrique, que le module lit avec
       `toString()`. Les chemins sont donc portés dans des **chaînes** : Vite
       refuserait à la compilation un import vers un module inexistant, et un
       commentaire ne survivrait pas — esbuild les retire avant que
       `toString()` ne s'exécute. */
    const premier = lazyWithRetry(() => {
      const chemin = "import('./PageA')"
      return Promise.reject(new Error(chemin))
    })
    const second = lazyWithRetry(() => {
      const chemin = "import('./PageB')"
      return Promise.reject(new Error(chemin))
    })

    void charger(premier).catch(() => undefined)
    await vi.advanceTimersByTimeAsync(0)
    void charger(second).catch(() => undefined)
    await vi.advanceTimersByTimeAsync(0)

    const cles = Object.keys(sessionStorage).filter((k) => k.startsWith('chunk_reload_'))
    expect(cles).toHaveLength(2)
    expect(cles.some((k) => k.includes('PageA'))).toBe(true)
    expect(cles.some((k) => k.includes('PageB'))).toBe(true)
  })
})


describe('chemin indéterminable', () => {
  it('deux modules sans chemin lisible se partagent une seule clé', async () => {
    /* Le code dérive sa clé du texte de la fabrique. Quand aucun `import(...)`
       n'y est reconnaissable, il retombe sur `chunk_reload_global` — commune à
       tous. Deux pages périmées dans la même session n'obtiennent alors qu'un
       seul rattrapage : la seconde consomme la clé posée par la première et
       laisse l'erreur remonter.

       Le cas est marginal — les fabriques réelles contiennent bien leur
       `import('@/pages/…')` — mais il explique pourquoi la clé est dérivée du
       chemin plutôt que d'un compteur global. */
    const sansChemin = () => Promise.reject(new Error('chunk absent'))
    const premier = lazyWithRetry(sansChemin)
    const second = lazyWithRetry(sansChemin)

    void charger(premier).catch(() => undefined)
    await vi.advanceTimersByTimeAsync(0)
    const erreurSeconde = charger(second).catch((e) => e)
    await vi.advanceTimersByTimeAsync(0)

    await expect(erreurSeconde).resolves.toBeInstanceOf(Error)
    expect(rechargements.nombre).toBe(1)
  })
})
