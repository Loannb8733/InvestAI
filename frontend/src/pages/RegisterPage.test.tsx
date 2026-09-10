import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import RegisterPage from './RegisterPage'

/**
 * L'inscription — 436 lignes, **0 %**.
 *
 * C'est le premier contact avec le produit, et le seul écran où une erreur
 * silencieuse fait perdre l'utilisateur pour de bon : personne ne recommence
 * un formulaire qui n'a rien répondu.
 *
 * Deux choses s'y jouent, que ce filet fixe :
 *
 * - la règle de mot de passe, qui doit être **exactement** celle du serveur —
 *   dix caractères, une majuscule, un chiffre (NEW-67 a montré ce qu'un
 *   désaccord coûte) ;
 * - les **trois** réponses possibles du serveur. La troisième est née de
 *   l'anti-énumération : quand la réponse ne dit pas si l'adresse était libre,
 *   l'auto-connexion est impossible, et l'écran restait muet — ni message, ni
 *   redirection.
 */

const inscrire = vi.hoisted(() => vi.fn())
const renvoyerVerification = vi.hoisted(() => vi.fn())
const toastMock = vi.hoisted(() => vi.fn())
const naviguer = vi.hoisted(() => vi.fn())
const poserJetons = vi.hoisted(() => vi.fn())
const chargerUtilisateur = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/api')>()),
  authApi: { register: inscrire, resendVerification: renvoyerVerification },
}))
vi.mock('@/hooks/use-toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('@/components/ui/aurora-canvas', () => ({ default: () => null }))
vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({ setTokens: poserJetons, fetchUser: chargerUtilisateur }),
}))
vi.mock('react-router-dom', async () => {
  const reel = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...reel, useNavigate: () => naviguer }
})

function afficher() {
  return render(
    <MemoryRouter>
      <RegisterPage />
    </MemoryRouter>,
  )
}

/** Remplit le formulaire et le soumet. */
async function sInscrire({
  email = 'nouveau@test.com',
  motDePasse = 'MotDePasseValide1',
  confirmation,
  accepterConditions = true,
}: {
  email?: string
  motDePasse?: string
  confirmation?: string
  accepterConditions?: boolean
} = {}) {
  const confirmationSaisie = confirmation ?? motDePasse
  fireEvent.change(screen.getByLabelText(/Adresse email/i), { target: { value: email } })
  fireEvent.change(screen.getByLabelText(/^Mot de passe/i), { target: { value: motDePasse } })
  fireEvent.change(screen.getByLabelText(/Confirmer/i), { target: { value: confirmationSaisie } })
  if (accepterConditions) fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.submit(screen.getByRole('button', { name: /Créer mon compte|S'inscrire/i }).closest('form')!)
}

beforeEach(() => {
  vi.clearAllMocks()
  inscrire.mockResolvedValue({ email_verification_required: true })
})

describe('ce que le formulaire refuse avant d’appeler le serveur', () => {
  it('exige une adresse valide', async () => {
    afficher()

    await sInscrire({ email: 'pas-une-adresse' })

    expect(await screen.findByText(/Email invalide/i)).toBeInTheDocument()
    expect(inscrire).not.toHaveBeenCalled()
  })

  it.each([
    // « Motdepas1 » fait exactement **neuf** caractères : il satisfait toutes
    // les autres règles et ne tombe que sur la longueur. Un mot de passe plus
    // court serait refusé par n'importe quel minimum, et le test passerait
    // aussi bien avec un seuil à huit qu'à dix.
    ['Motdepas1', /Minimum 10/i],
    ['minusculesetun1', /majuscule/i],
    ['SansAucunChiffre', /chiffre/i],
  ])('refuse « %s » avec le motif qui convient', async (faible, motif) => {
    // La même règle que le serveur, dite avant l'aller-retour : l'utilisateur
    // voit ce qui manque au lieu d'un refus après coup.
    afficher()

    await sInscrire({ motDePasse: faible })

    expect(await screen.findByText(motif)).toBeInTheDocument()
    expect(inscrire).not.toHaveBeenCalled()
  })

  it('exige que les deux saisies concordent', async () => {
    afficher()

    await sInscrire({ motDePasse: 'MotDePasseValide1', confirmation: 'MotDePasseValide2' })

    expect(await screen.findByText(/ne correspondent pas/i)).toBeInTheDocument()
    expect(inscrire).not.toHaveBeenCalled()
  })

  it('exige l’acceptation des conditions', async () => {
    afficher()

    await sInscrire({ accepterConditions: false })

    expect(await screen.findByText(/accepter les conditions/i)).toBeInTheDocument()
    expect(inscrire).not.toHaveBeenCalled()
  })

  it('accepte un mot de passe conforme sans exiger de symbole', async () => {
    // La règle n'en demande pas : l'exiger ici divergerait du serveur, qui
    // accepterait ce que l'écran refuse.
    afficher()

    await sInscrire({ motDePasse: 'SansSymbole11' })

    await waitFor(() => expect(inscrire).toHaveBeenCalled())
  })
})

describe('les trois réponses possibles du serveur', () => {
  it('invite à vérifier l’adresse quand un lien a été envoyé', async () => {
    inscrire.mockResolvedValue({ email_verification_required: true })
    afficher()

    await sInscrire({ email: 'nouveau@test.com' })

    expect(await screen.findByText(/Vérifiez votre email/i)).toBeInTheDocument()
    expect(screen.getByText('nouveau@test.com')).toBeInTheDocument()
    expect(screen.getByText(/valable 24 heures/i)).toBeInTheDocument()
  })

  it('connecte directement quand le serveur rend des jetons', async () => {
    inscrire.mockResolvedValue({ access_token: 'jeton-acces', refresh_token: 'jeton-refraichissement' })
    afficher()

    await sInscrire()

    await waitFor(() => expect(poserJetons).toHaveBeenCalledWith('jeton-acces', 'jeton-refraichissement'))
    expect(chargerUtilisateur).toHaveBeenCalled()
    expect(naviguer).toHaveBeenCalledWith('/')
  })

  it('ne laisse pas l’écran muet sur une réponse neutre', async () => {
    // La réponse ne dit pas si l'adresse était libre (anti-énumération), donc
    // ni jeton ni vérification. Sans cette branche, le formulaire ne répondait
    // rien du tout et l'utilisateur restait devant un écran figé.
    inscrire.mockResolvedValue({ message: 'Connectez-vous avec cette adresse.' })
    afficher()

    await sInscrire()

    await waitFor(() => expect(naviguer).toHaveBeenCalledWith('/login'))
    expect(toastMock.mock.calls.at(-1)![0].description).toMatch(/Connectez-vous/i)
  })

  it('affiche la raison donnée par le serveur en cas de refus', async () => {
    inscrire.mockRejectedValue({ response: { data: { detail: 'Adresse déjà utilisée.' } } })
    afficher()

    await sInscrire()

    await waitFor(() => expect(toastMock).toHaveBeenCalled())
    const message = toastMock.mock.calls.at(-1)![0]
    expect(message.variant).toBe('destructive')
    expect(screen.getByText(/Adresse déjà utilisée/i)).toBeInTheDocument()
  })

  it('reste utilisable après un échec', async () => {
    // Le bouton doit se relâcher : sinon l'utilisateur ne peut pas corriger sa
    // saisie et réessayer.
    inscrire.mockRejectedValue(new Error('réseau'))
    afficher()

    await sInscrire()

    await waitFor(() => expect(toastMock).toHaveBeenCalled())
    const bouton = screen.getByRole('button', { name: /Créer mon compte|S'inscrire/i })
    expect(bouton).not.toBeDisabled()
  })
})

describe('l’écran d’attente de vérification', () => {
  async function atteindre() {
    afficher()
    await sInscrire({ email: 'nouveau@test.com' })
    await screen.findByText(/Vérifiez votre email/i)
  }

  it('permet de redemander le lien', async () => {
    renvoyerVerification.mockResolvedValue({})
    await atteindre()

    fireEvent.click(screen.getByRole('button', { name: /Renvoyer le lien/i }))

    await waitFor(() => expect(renvoyerVerification).toHaveBeenCalledWith('nouveau@test.com'))
  })

  it('mène à la connexion', async () => {
    await atteindre()

    fireEvent.click(screen.getByRole('button', { name: /Aller à la connexion/i }))

    expect(naviguer).toHaveBeenCalledWith('/login')
  })
})
