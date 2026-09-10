import { StrictMode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import VerifyEmailPage from './VerifyEmailPage'

/**
 * L'écran d'atterrissage du lien de vérification — 145 lignes, **0 %**.
 *
 * Il complète le parcours d'inscription : après « Vérifiez votre email »,
 * l'utilisateur clique le lien reçu et arrive ici. Rien d'autre ne se passe sur
 * cette page qu'un appel automatique au serveur, dont dépend l'activation du
 * compte.
 *
 * Le point délicat n'est pas visible à la lecture : le jeton est **à usage
 * unique**, et React 18 monte deux fois chaque composant en développement. Sans
 * la garde qui n'autorise qu'un seul appel, la seconde tentative se ferait
 * refuser et l'écran annoncerait un échec après une vérification réussie.
 */

const verifierEmail = vi.hoisted(() => vi.fn())
const toastMock = vi.hoisted(() => vi.fn())
const naviguer = vi.hoisted(() => vi.fn())
const poserJetons = vi.hoisted(() => vi.fn())
const chargerUtilisateur = vi.hoisted(() => vi.fn())
let parametresUrl = new URLSearchParams()

vi.mock('@/services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/api')>()),
  authApi: { verifyEmail: verifierEmail },
}))
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('@/components/ui/aurora-canvas', () => ({ default: () => null }))
vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({ setTokens: poserJetons, fetchUser: chargerUtilisateur }),
}))
vi.mock('react-router-dom', async () => {
  const reel = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...reel, useNavigate: () => naviguer, useSearchParams: () => [parametresUrl, vi.fn()] }
})

function afficher() {
  return render(
    <MemoryRouter>
      <VerifyEmailPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  parametresUrl = new URLSearchParams('token=jeton-du-courriel')
  verifierEmail.mockResolvedValue({ access_token: 'jeton-acces', refresh_token: 'jeton-refraichissement' })
})

describe('la vérification automatique', () => {
  it('appelle le serveur avec le jeton du lien, sans rien demander', async () => {
    afficher()

    await waitFor(() => expect(verifierEmail).toHaveBeenCalledWith('jeton-du-courriel'))
  })

  it("n'appelle le serveur qu'une seule fois, meme monte deux fois", async () => {
    // Le jeton ne sert qu'une fois. React 18 exécute deux fois chaque effet
    // sous `StrictMode` — le mode de développement du projet : sans la garde,
    // le second appel se ferait refuser et l'écran annoncerait un échec après
    // une vérification pourtant réussie.
    //
    // Un simple nouveau rendu ne suffirait pas à le montrer : les dépendances
    // de l'effet sont stables, il ne se relancerait pas.
    render(
      <StrictMode>
        <MemoryRouter>
          <VerifyEmailPage />
        </MemoryRouter>
      </StrictMode>,
    )

    await waitFor(() => expect(verifierEmail).toHaveBeenCalled())
    expect(verifierEmail).toHaveBeenCalledTimes(1)
  })

  it('montre une attente tant que le serveur n’a pas répondu', () => {
    verifierEmail.mockReturnValue(new Promise(() => {}))
    afficher()

    expect(screen.getByText(/Vérification en cours/i)).toBeInTheDocument()
  })
})

describe('quand la vérification réussit', () => {
  it('connecte l’utilisateur dans la foulée', async () => {
    // Il vient de prouver qu'il possède l'adresse : lui redemander ses
    // identifiants n'apporterait rien.
    afficher()

    await waitFor(() => expect(poserJetons).toHaveBeenCalledWith('jeton-acces', 'jeton-refraichissement'))
    expect(chargerUtilisateur).toHaveBeenCalled()
  })

  it('annonce l’activation et mène au tableau de bord', async () => {
    afficher()

    expect(await screen.findByText(/Email vérifié/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /tableau de bord/i }))
    expect(naviguer).toHaveBeenCalledWith('/')
  })

  it('se passe des jetons quand le serveur n’en renvoie pas', async () => {
    // La vérification reste un succès même sans connexion automatique : le
    // compte est actif, l'utilisateur ira se connecter.
    verifierEmail.mockResolvedValue({ message: 'Compte activé.' })
    afficher()

    expect(await screen.findByText(/Email vérifié/i)).toBeInTheDocument()
    expect(poserJetons).not.toHaveBeenCalled()
  })
})

describe('quand la vérification échoue', () => {
  it('refuse un lien sans jeton sans appeler le serveur', async () => {
    parametresUrl = new URLSearchParams()
    afficher()

    expect(await screen.findByText(/Lien de vérification invalide/i)).toBeInTheDocument()
    expect(verifierEmail).not.toHaveBeenCalled()
  })

  it('affiche la raison donnée par le serveur', async () => {
    // « Lien expiré » et « déjà utilisé » appellent des gestes différents :
    // demander un nouveau lien, ou simplement se connecter.
    verifierEmail.mockRejectedValue({ response: { data: { detail: 'Le lien a expiré.' } } })
    afficher()

    expect(await screen.findByText(/Le lien a expiré/i)).toBeInTheDocument()
    expect(screen.getByText(/Vérification échouée/i)).toBeInTheDocument()
  })

  it('retombe sur un message générique quand le serveur n’en donne aucun', async () => {
    verifierEmail.mockRejectedValue(new Error('réseau'))
    afficher()

    expect(await screen.findByText(/invalide ou a expiré/i)).toBeInTheDocument()
  })

  it('propose de recommencer l’inscription', async () => {
    verifierEmail.mockRejectedValue(new Error('réseau'))
    afficher()
    await screen.findByText(/Vérification échouée/i)

    fireEvent.click(screen.getByRole('button', { name: /S'inscrire à nouveau/i }))

    expect(naviguer).toHaveBeenCalledWith('/register')
  })

  it('ne connecte personne', async () => {
    verifierEmail.mockRejectedValue(new Error('réseau'))
    afficher()
    await screen.findByText(/Vérification échouée/i)

    expect(poserJetons).not.toHaveBeenCalled()
    expect(chargerUtilisateur).not.toHaveBeenCalled()
  })
})
