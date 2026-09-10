import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosRequestConfig } from 'axios'

/**
 * Les trois intercepteurs de la couche d'appel.
 *
 * `api.ts` fait 1 676 lignes dont **0,49 % de fonctions couvertes**. L'essentiel
 * n'y est pourtant pas dans les 197 appels — chacun se contente de passer une
 * URL — mais dans les trois intercepteurs qui gouvernent *toutes* les requêtes :
 *
 * - un réessai sur panne réseau ou serveur indisponible ;
 * - l'ajout du jeton d'authentification ;
 * - le rafraîchissement du jeton sur 401, avec une file d'attente pour que
 *   plusieurs requêtes simultanées n'en déclenchent qu'un seul.
 *
 * Une erreur là se propage à l'application entière, et l'état partagé
 * (`isRefreshing`, `failedQueue`) rend le troisième particulièrement délicat.
 *
 * Les tests remplacent l'`adapter` de l'instance : le vrai chemin est parcouru,
 * intercepteurs compris, sans réseau.
 */

const rafraichir = vi.hoisted(() => vi.fn())
const deconnecter = vi.hoisted(() => vi.fn())
const etatAuth = vi.hoisted(() => ({ accessToken: null as string | null }))
const toastMock = vi.hoisted(() => vi.fn())

vi.mock('@/stores/authStore', () => ({
  useAuthStore: {
    getState: () => ({
      accessToken: etatAuth.accessToken,
      refreshAccessToken: rafraichir,
      logout: deconnecter,
    }),
  },
}))
vi.mock('@/hooks/use-toast', () => ({ toast: toastMock }))

const { default: api } = await import('./api')

type Reponse = { status: number; data?: unknown }
let scenario: Array<Reponse | 'reseau'> = []
let requetes: AxiosRequestConfig[] = []

function transport(config: AxiosRequestConfig) {
  requetes.push(config)
  const prochain = scenario.shift() ?? { status: 200, data: {} }
  if (prochain === 'reseau') {
    return Promise.reject(Object.assign(new Error('Network Error'), { config, isAxiosError: true }))
  }
  const reponse = {
    data: prochain.data ?? {},
    status: prochain.status,
    statusText: '',
    headers: {},
    config,
  }
  return prochain.status >= 400
    ? Promise.reject(
        Object.assign(new Error(`HTTP ${prochain.status}`), { config, response: reponse, isAxiosError: true }),
      )
    : Promise.resolve(reponse)
}

beforeEach(() => {
  scenario = []
  requetes = []
  etatAuth.accessToken = null
  vi.clearAllMocks()
  // @ts-expect-error — l'adaptateur d'axios accepte une fonction
  api.defaults.adapter = transport
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

/** Laisse les promesses et les minuteries se dénouer (le réessai attend 3 s). */
async function laisserPasser(ms = 10000) {
  await vi.advanceTimersByTimeAsync(ms)
}

describe('ajout du jeton', () => {
  it('attache le jeton courant à chaque requête', async () => {
    etatAuth.accessToken = 'jeton-abc'
    scenario = [{ status: 200 }]

    await api.get('/portfolios')

    expect(requetes[0].headers?.Authorization).toBe('Bearer jeton-abc')
  })

  it("n'attache rien quand la session est vide", async () => {
    scenario = [{ status: 200 }]

    await api.get('/portfolios')

    expect(requetes[0].headers?.Authorization).toBeUndefined()
  })
})

describe('réessai sur panne', () => {
  it('retente deux fois une panne réseau, puis abandonne', async () => {
    scenario = ['reseau', 'reseau', 'reseau']

    const promesse = api.get('/portfolios').catch((e) => e)
    await laisserPasser()

    expect(requetes).toHaveLength(3) // 1 tentative + 2 reprises
    await expect(promesse).resolves.toBeInstanceOf(Error)
  })

  it("s'arrête dès qu'une reprise aboutit", async () => {
    scenario = ['reseau', { status: 200, data: { ok: true } }]

    const promesse = api.get('/portfolios')
    await laisserPasser()

    await expect(promesse).resolves.toMatchObject({ data: { ok: true } })
    expect(requetes).toHaveLength(2)
  })

  it('retente aussi un serveur indisponible', async () => {
    // 502 et 503 signalent un serveur qui redémarre. L'hébergement met les
    // instances gratuites en veille : la première requête au réveil échoue
    // ainsi, et c'est précisément le cas que le réessai rattrape.
    scenario = [{ status: 503 }, { status: 200 }]

    const promesse = api.get('/portfolios')
    await laisserPasser()

    await expect(promesse).resolves.toMatchObject({ status: 200 })
  })

  it('ne retente jamais le sondage des notifications', async () => {
    /* Ces requêtes partent en boucle en arrière-plan : les rejouer
       inonderait un serveur déjà en difficulté. */
    scenario = ['reseau', { status: 200 }]

    const promesse = api.get('/notifications/count').catch((e) => e)
    await laisserPasser()

    expect(requetes).toHaveLength(1)
    await expect(promesse).resolves.toBeInstanceOf(Error)
  })

  it("ne retente pas une erreur que le serveur a formulée", async () => {
    // Un 404 ou un 422 est une réponse, pas une panne : la rejouer donnerait
    // le même résultat.
    scenario = [{ status: 404 }]

    await api.get('/portfolios').catch(() => undefined)
    await laisserPasser()

    expect(requetes).toHaveLength(1)
  })
})

describe('rafraîchissement du jeton', () => {
  it('rejoue la requête avec le nouveau jeton après un 401', async () => {
    rafraichir.mockImplementation(async () => {
      etatAuth.accessToken = 'jeton-neuf'
    })
    scenario = [{ status: 401 }, { status: 200, data: { ok: true } }]

    const promesse = api.get('/portfolios')
    await laisserPasser()

    await expect(promesse).resolves.toMatchObject({ data: { ok: true } })
    expect(rafraichir).toHaveBeenCalledTimes(1)
    expect(requetes[1].headers?.Authorization).toBe('Bearer jeton-neuf')
  })

  it("ne rafraîchit qu'une fois pour plusieurs 401 simultanés", async () => {
    /* La file d'attente est la raison d'être de `isRefreshing`. Sans elle,
       trois écrans qui chargent ensemble déclencheraient trois
       rafraîchissements concurrents — et deux jetons sur trois seraient
       aussitôt périmés. */
    rafraichir.mockImplementation(async () => {
      etatAuth.accessToken = 'jeton-neuf'
    })
    scenario = [{ status: 401 }, { status: 401 }, { status: 401 }, { status: 200 }, { status: 200 }, { status: 200 }]

    const promesses = [api.get('/a'), api.get('/b'), api.get('/c')].map((p) => p.catch((e) => e))
    await laisserPasser()
    await Promise.all(promesses)

    expect(rafraichir).toHaveBeenCalledTimes(1)
  })

  it('déconnecte quand le rafraîchissement échoue', async () => {
    rafraichir.mockRejectedValue(new Error('refresh token expiré'))
    scenario = [{ status: 401 }]

    await api.get('/portfolios').catch(() => undefined)
    await laisserPasser()

    expect(deconnecter).toHaveBeenCalled()
  })

  it("déconnecte aussi quand le rafraîchissement ne rend aucun jeton", async () => {
    // Réponse acceptée mais sans jeton : le cas est distinct d'un échec, et
    // sans ce traitement la requête repartirait avec l'ancien jeton, en
    // boucle.
    rafraichir.mockResolvedValue(undefined)
    scenario = [{ status: 401 }]

    await api.get('/portfolios').catch(() => undefined)
    await laisserPasser()

    expect(deconnecter).toHaveBeenCalled()
  })

  it("dit pourquoi la session s'est fermée quand le mot de passe a changé", async () => {
    // NEW-65 : changer son mot de passe coupe les sessions ouvertes ailleurs.
    // Sans ce message, l'utilisateur se retrouve devant l'écran de connexion
    // sans savoir pourquoi — alors que le serveur, lui, l'a dit.
    rafraichir.mockRejectedValue({
      response: { data: { detail: 'Session expirée : le mot de passe a été modifié.' } },
    })
    scenario = [{ status: 401 }]

    await api.get('/portfolios').catch(() => undefined)
    await laisserPasser()

    expect(deconnecter).toHaveBeenCalled()
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Session expirée', variant: 'destructive' }),
    )
  })

  it("ne parle pas de mot de passe quand la session a simplement expiré", async () => {
    // Un jeton arrivé au bout de sa durée de vie n'appelle pas d'explication :
    // annoncer un changement de mot de passe inquiéterait pour rien.
    rafraichir.mockRejectedValue({ response: { data: { detail: 'Token has been revoked' } } })
    scenario = [{ status: 401 }]

    await api.get('/portfolios').catch(() => undefined)
    await laisserPasser()

    expect(deconnecter).toHaveBeenCalled()
    expect(toastMock).not.toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Session expirée' }),
    )
  })

  it("ne tente pas de rafraîchir un rafraîchissement refusé", async () => {
    /* Sans cette exception, un refresh token périmé provoquerait une boucle :
       401 sur `/auth/refresh` → rafraîchir → 401 → … */
    scenario = [{ status: 401 }]

    await api.post('/auth/refresh').catch(() => undefined)
    await laisserPasser()

    expect(rafraichir).not.toHaveBeenCalled()
  })
})

describe('signalement des erreurs', () => {
  it.each([
    [422, 'Erreur de validation'],
    [500, 'Erreur serveur'],
    [403, 'Accès refusé'],
  ])('un %i affiche « %s »', async (statut, titre) => {
    scenario = [{ status: statut }]

    await api.get('/portfolios').catch(() => undefined)
    await laisserPasser()

    expect(toastMock).toHaveBeenCalledWith(expect.objectContaining({ title: titre }))
  })

  it('laisse le 404 aux appelants', async () => {
    // Une ressource absente se traite au cas par cas — un projet supprimé,
    // une page qui sonde une donnée facultative. Un message global y serait
    // du bruit.
    scenario = [{ status: 404 }]

    await api.get('/portfolios').catch(() => undefined)
    await laisserPasser()

    expect(toastMock).not.toHaveBeenCalled()
  })

  it("reprend le message du serveur quand il en donne un", async () => {
    scenario = [{ status: 422, data: { detail: 'Le montant doit être positif' } }]

    await api.get('/portfolios').catch(() => undefined)
    await laisserPasser()

    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({ description: 'Le montant doit être positif' }),
    )
  })
})
