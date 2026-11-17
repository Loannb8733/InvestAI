const ROLE_LABELS: Record<string, string> = { admin: 'Administrateur', user: 'Utilisateur' }

export const roleLabel = (role: string | undefined) => (role ? (ROLE_LABELS[role] ?? role) : '')
