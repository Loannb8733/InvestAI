import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/hooks/use-toast'
import { queryKeys } from '@/lib/queryKeys'
import { apiClient } from '@/shared/api/client'
import { serverMessage } from '@/shared/api/errors'
import { useAuthStore } from '@/stores/authStore'
import type { InvestorProfile, MfaSetup, Profile, ProfileUpdate, RiskProfile, UserCreate } from './types'

export const investorProfileQueryKey = ['auth', 'investor-profile'] as const

const toInvestorProfile = (profile: Profile): InvestorProfile => ({
  tmi_rate: profile.tmi_rate ?? null,
  risk_profile: (profile.risk_profile as RiskProfile | null | undefined) ?? null,
  monthly_dca_eur: profile.monthly_dca_eur ?? null,
})

export function useInvestorProfile(staleTime: number) {
  return useQuery({
    queryKey: investorProfileQueryKey,
    queryFn: async () => toInvestorProfile(await apiClient.get('/auth/me', { silent: true })),
    staleTime,
    meta: { suppressGlobalError: true },
  })
}

function useApplyProfile() {
  const queryClient = useQueryClient()
  const applyProfile = useAuthStore((state) => state.applyProfile)
  return (profile: Profile) => {
    applyProfile(profile)
    queryClient.setQueryData(investorProfileQueryKey, toInvestorProfile(profile))
  }
}

export function useUpdateProfile() {
  const { toast } = useToast()
  const apply = useApplyProfile()
  return useMutation({
    mutationFn: (body: ProfileUpdate) => apiClient.patch('/auth/me', { body, silent: true }),
    onSuccess: (profile) => {
      apply(profile)
      toast({ title: 'Profil mis à jour', description: 'Vos informations ont été enregistrées.' })
    },
    onError: () => {
      toast({ title: 'Erreur', description: 'Impossible de mettre à jour le profil.', variant: 'destructive' })
    },
  })
}

export function useUpdateInvestorProfile() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: InvestorProfile) => apiClient.patch('/auth/me', { body, silent: true }),
    onSuccess: (profile) => {
      queryClient.setQueryData(investorProfileQueryKey, toInvestorProfile(profile))
      toast({ title: 'Profil investisseur mis à jour', description: 'Vos paramètres financiers ont été enregistrés.' })
    },
    onError: () => {
      toast({ title: 'Erreur', description: "Impossible d'enregistrer le profil investisseur.", variant: 'destructive' })
    },
  })
}

export function useChangePassword(onDone: () => void) {
  const { toast } = useToast()
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      apiClient.post('/auth/change-password', { body, silent: true }),
    onSuccess: () => {
      onDone()
      toast({ title: 'Mot de passe modifié', description: 'Votre mot de passe a été mis à jour.' })
    },
    onError: (error: unknown) => {
      toast({ title: 'Erreur', description: serverMessage(error) ?? 'Mot de passe actuel incorrect.', variant: 'destructive' })
    },
  })
}

export function useMfaSetup(onReady: (setup: MfaSetup) => void) {
  const { toast } = useToast()
  return useMutation({
    mutationFn: () => apiClient.post('/auth/mfa/setup', { silent: true }),
    onSuccess: onReady,
    onError: () => {
      toast({ title: 'Erreur', description: 'Impossible de configurer la MFA.', variant: 'destructive' })
    },
  })
}

export function useMfaCode(action: 'verify' | 'disable', onDone: () => void) {
  const { toast } = useToast()
  const fetchCurrentUser = useAuthStore((state) => state.fetchCurrentUser)
  return useMutation({
    mutationFn: (code: string) =>
      action === 'verify'
        ? apiClient.post('/auth/mfa/verify', { body: { code }, silent: true })
        : apiClient.post('/auth/mfa/disable', { body: { code }, silent: true }),
    onSuccess: () => {
      onDone()
      fetchCurrentUser()
      toast(
        action === 'verify'
          ? { title: 'MFA activée', description: "L'authentification à deux facteurs est maintenant active." }
          : { title: 'MFA désactivée', description: "L'authentification à deux facteurs a été désactivée." }
      )
    },
    onError: () => {
      toast({ title: 'Code invalide', description: 'Veuillez vérifier le code et réessayer.', variant: 'destructive' })
    },
  })
}

export function useUsers() {
  return useQuery({
    queryKey: queryKeys.admin.users,
    queryFn: () => apiClient.get('/users', { silent: true }),
    meta: { suppressGlobalError: true },
  })
}

export function useUserMutations(onCreated: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.admin.users })

  const create = useMutation({
    mutationFn: (body: UserCreate) => apiClient.post('/users', { body, silent: true }),
    onSuccess: () => {
      refresh()
      onCreated()
      toast({ title: 'Utilisateur créé' })
    },
    onError: (error: unknown) => {
      toast({ variant: 'destructive', title: 'Erreur', description: serverMessage(error) ?? "Impossible de créer l'utilisateur." })
    },
  })

  const setActive = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      apiClient.patch('/users/{user_id}', { path: { user_id: id }, body: { is_active }, silent: true }),
    onSuccess: () => {
      refresh()
      toast({ title: 'Statut mis à jour' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur lors de la mise à jour' })
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => apiClient.delete('/users/{user_id}', { path: { user_id: id }, silent: true }),
    onSuccess: () => {
      refresh()
      toast({ title: 'Utilisateur supprimé' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur lors de la suppression' })
    },
  })

  return { create, setActive, remove }
}
