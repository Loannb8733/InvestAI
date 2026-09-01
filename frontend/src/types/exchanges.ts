/**
 * Types du domaine « exchanges », extraits de `ExchangesPage.tsx` (ARC-07).
 *
 * Ils décrivent le contrat de l'API, pas le rendu : les garder dans un composant de
 * 1 300 lignes les rendait invisibles à toute autre page qui en aurait besoin.
 */

/** Une plateforme supportée, telle que décrite par le backend. */
export interface Exchange {
  id: string
  name: string
  requires_secret: boolean
  requires_passphrase: boolean
  description: string
}

/** Une clé API enregistrée par l'utilisateur pour une plateforme. */
export interface APIKey {
  id: string
  exchange: string
  label: string | null
  is_active: boolean
  /** Dernière synchronisation réussie, `null` si aucune n'a encore abouti. */
  last_sync_at: string | null
  /** Message de la dernière erreur de synchronisation, `null` si tout va bien. */
  last_error: string | null
  created_at: string
}

/** Résultat d'un test de connexion à une plateforme. */
export interface TestResult {
  success: boolean
  message: string
  /** Soldes renvoyés par la plateforme quand le test réussit. */
  balance?: Record<string, number>
}
