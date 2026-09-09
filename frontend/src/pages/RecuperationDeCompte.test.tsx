import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ForgotPasswordPage from './ForgotPasswordPage'
import ResetPasswordPage from './ResetPasswordPage'

/**
 * Le parcours par lequel on reprend la main sur son compte.
 *
 * Les deux pages étaient à **0 %** — 110 et 139 lignes — alors qu'elles forment
 * le pendant visible des routes `forgot-password` et `reset-password` que le
 * filet serveur vient de couvrir. C'est le seul chemin dont dispose quelqu'un
 * qui ne peut plus se connecter : s'il échoue en silence, il n'y a pas de
 * recours.
 *
 * Deux choses comptent ici et se voient à l'écran : la page **ne dit jamais**
 * si un compte existe (le pendant de l'anti-énumération côté serveur), et elle
 * refuse elle-même les mots de passe que le serveur refuserait — même règle,
 * dix caractères, une majuscule, un chiffre — plutôt que de laisser
 * l'utilisateur découvrir le refus après un aller-retour.
 */

const posterApi = vi.hoisted(() => vi.fn())
const toastMock = vi.hoisted(() => vi.fn())
const naviguer = vi.hoisted(() => vi.fn())
let parametresUrl = new URLSearchParams()

vi.mock('@/services/api', () => ({ default: { post: posterApi } }))
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: toastMock }) }))
// Le fond animé peint sur un canvas WebGL, que jsdom ne fournit pas.
vi.mock('@/components/ui/aurora-canvas', () => ({ default: () => null }))
vi.mock('react-router-dom', async () => {
  const reel = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...reel,
    useNavigate: () => naviguer,
    useSearchParams: () => [parametresUrl, vi.fn()],
  }
})

function afficher(page: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{page}</MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  parametresUrl = new URLSearchParams()
})

describe('la demande de réinitialisation', () => {
  function saisirEmail(adresse: string) {
    fireEvent.change(screen.getByLabelText(/Adresse email/i), { target: { value: adresse } })
  }

  it("n'envoie rien tant qu'aucune adresse n'est saisie", () => {
    afficher(<ForgotPasswordPage />)

    expect(screen.getByRole('button', { name: /Envoyer le lien/i })).toBeDisabled()
  })

  it("transmet l'adresse saisie au serveur", async () => {
    posterApi.mockResolvedValue({ data: {} })
    afficher(<ForgotPasswordPage />)

    saisirEmail('titulaire@test.com')
    fireEvent.click(screen.getByRole('button', { name: /Envoyer le lien/i }))

    await waitFor(() =>
      expect(posterApi).toHaveBeenCalledWith('/auth/forgot-password', { email: 'titulaire@test.com' }),
    )
  })

  it('ne dit pas si le compte existe', async () => {
    // Le pendant de l'anti-énumération : la confirmation reste conditionnelle
    // (« Si un compte existe… ») quelle que soit l'adresse.
    posterApi.mockResolvedValue({ data: {} })
    afficher(<ForgotPasswordPage />)

    saisirEmail('inconnu@test.com')
    fireEvent.click(screen.getByRole('button', { name: /Envoyer le lien/i }))

    expect(await screen.findByText(/Si un compte existe/i)).toBeInTheDocument()
    expect(screen.getByText(/inconnu@test.com/)).toBeInTheDocument()
  })

  it("annonce la durée de validité du lien", async () => {
    // Sans quoi l'utilisateur qui ouvre son courrier le lendemain ne comprend
    // pas pourquoi le lien ne marche plus.
    posterApi.mockResolvedValue({ data: {} })
    afficher(<ForgotPasswordPage />)

    saisirEmail('titulaire@test.com')
    fireEvent.click(screen.getByRole('button', { name: /Envoyer le lien/i }))

    expect(await screen.findByText(/valable 1 heure/i)).toBeInTheDocument()
  })

  it("permet de recommencer avec une autre adresse", async () => {
    posterApi.mockResolvedValue({ data: {} })
    afficher(<ForgotPasswordPage />)
    saisirEmail('faute-de-frappe@test.com')
    fireEvent.click(screen.getByRole('button', { name: /Envoyer le lien/i }))
    await screen.findByText(/Si un compte existe/i)

    fireEvent.click(screen.getByRole('button', { name: /Envoyer à une autre adresse/i }))

    const champ = screen.getByLabelText(/Adresse email/i) as HTMLInputElement
    expect(champ.value).toBe('')
  })

  it("ne prétend pas avoir envoyé le lien quand l'appel échoue", async () => {
    // La confirmation ne doit pas s'afficher sur une panne : l'utilisateur
    // attendrait un courrier qui ne viendra pas.
    posterApi.mockRejectedValue(new Error('réseau'))
    afficher(<ForgotPasswordPage />)

    saisirEmail('titulaire@test.com')
    fireEvent.click(screen.getByRole('button', { name: /Envoyer le lien/i }))

    await waitFor(() => expect(toastMock).toHaveBeenCalled())
    expect(toastMock.mock.calls.at(-1)![0].variant).toBe('destructive')
    expect(screen.queryByText(/Si un compte existe/i)).not.toBeInTheDocument()
  })
})

describe('le choix du nouveau mot de passe', () => {
  function saisir(mot: string, confirmation = mot) {
    fireEvent.change(screen.getByLabelText(/^Nouveau mot de passe/i), { target: { value: mot } })
    fireEvent.change(screen.getByLabelText(/Confirmer le mot de passe/i), { target: { value: confirmation } })
  }

  function valider() {
    fireEvent.click(screen.getByRole('button', { name: /Réinitialiser le mot de passe/i }))
  }

  it('refuse de continuer sans jeton dans le lien', () => {
    afficher(<ResetPasswordPage />)

    expect(screen.getByText(/Lien de réinitialisation invalide/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/Nouveau mot de passe/i)).not.toBeInTheDocument()
  })

  it('transmet le jeton du lien avec le nouveau mot de passe', async () => {
    parametresUrl = new URLSearchParams('token=jeton-du-courriel')
    posterApi.mockResolvedValue({ data: {} })
    afficher(<ResetPasswordPage />)

    saisir('MotDePasseValide1')
    valider()

    await waitFor(() =>
      expect(posterApi).toHaveBeenCalledWith('/auth/reset-password', {
        token: 'jeton-du-courriel',
        new_password: 'MotDePasseValide1',
      }),
    )
  })

  it('signale deux saisies différentes sans rien envoyer', async () => {
    parametresUrl = new URLSearchParams('token=jeton')
    afficher(<ResetPasswordPage />)

    saisir('MotDePasseValide1', 'MotDePasseValide2')
    valider()

    expect(toastMock.mock.calls.at(-1)![0].description).toMatch(/ne correspondent pas/i)
    expect(posterApi).not.toHaveBeenCalled()
  })

  it.each([
    ['Court1', 'moins de dix caractères'],
    ['minusculesetun1', 'aucune majuscule'],
    ['SansAucunChiffre', 'aucun chiffre'],
  ])('refuse « %s » (%s) sans appeler le serveur', (faible) => {
    // Même règle que le serveur, appliquée avant l'aller-retour : l'utilisateur
    // voit tout de suite ce qui manque plutôt qu'un refus après coup.
    parametresUrl = new URLSearchParams('token=jeton')
    afficher(<ResetPasswordPage />)

    saisir(faible)
    valider()

    expect(toastMock.mock.calls.at(-1)![0].description).toMatch(/10 caractères, une majuscule et un chiffre/i)
    expect(posterApi).not.toHaveBeenCalled()
  })

  it('confirme la réinitialisation et propose de se connecter', async () => {
    parametresUrl = new URLSearchParams('token=jeton')
    posterApi.mockResolvedValue({ data: {} })
    afficher(<ResetPasswordPage />)

    saisir('MotDePasseValide1')
    valider()

    expect(await screen.findByText(/réinitialisé avec succès/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Se connecter/i }))
    expect(naviguer).toHaveBeenCalledWith('/login')
  })

  it('affiche la raison donnée par le serveur plutôt qu’un message passe-partout', async () => {
    // « Lien expiré » et « lien invalide » appellent des gestes différents :
    // en demander un nouveau, ou vérifier qu'on a ouvert le bon courriel.
    parametresUrl = new URLSearchParams('token=jeton-perime')
    posterApi.mockRejectedValue({
      response: { data: { detail: 'Lien de réinitialisation expiré. Veuillez en demander un nouveau.' } },
    })
    afficher(<ResetPasswordPage />)

    saisir('MotDePasseValide1')
    valider()

    await waitFor(() => expect(toastMock).toHaveBeenCalled())
    expect(toastMock.mock.calls.at(-1)![0].description).toMatch(/expiré/i)
  })

  it('retombe sur un message générique quand le serveur n’en donne aucun', async () => {
    parametresUrl = new URLSearchParams('token=jeton')
    posterApi.mockRejectedValue(new Error('réseau'))
    afficher(<ResetPasswordPage />)

    saisir('MotDePasseValide1')
    valider()

    await waitFor(() => expect(toastMock).toHaveBeenCalled())
    expect(toastMock.mock.calls.at(-1)![0].description).toBe('Une erreur est survenue.')
    expect(screen.queryByText(/réinitialisé avec succès/i)).not.toBeInTheDocument()
  })
})
