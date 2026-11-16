import { useEffect, useState } from 'react'
import { Loader2, TrendingUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import QueryErrorState from '@/components/ui/query-error-state'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { useInvestorProfile, useUpdateInvestorProfile } from '../hooks'
import type { RiskProfile } from '../types'

const TMI_OPTIONS = [
  { value: '0', label: '0 %' },
  { value: '0.11', label: '11 %' },
  { value: '0.3', label: '30 %' },
  { value: '0.41', label: '41 %' },
  { value: '0.45', label: '45 %' },
]

const RISK_OPTIONS: { value: RiskProfile; label: string }[] = [
  { value: 'conservative', label: 'Prudent' },
  { value: 'moderate', label: 'Modéré' },
  { value: 'aggressive', label: 'Agressif' },
]

const PROFILE_STALE_MS = 60_000

export default function InvestorProfileCard() {
  const { toast } = useToast()
  const profile = useInvestorProfile(PROFILE_STALE_MS)
  const update = useUpdateInvestorProfile()
  const [tmiRate, setTmiRate] = useState('')
  const [riskProfile, setRiskProfile] = useState('')
  const [monthlyDca, setMonthlyDca] = useState('')

  useEffect(() => {
    if (profile.data) {
      setTmiRate(profile.data.tmi_rate != null ? String(profile.data.tmi_rate) : '')
      setRiskProfile(profile.data.risk_profile ?? '')
      setMonthlyDca(profile.data.monthly_dca_eur != null ? String(profile.data.monthly_dca_eur) : '')
    }
  }, [profile.data])

  const save = () => {
    if (monthlyDca !== '') {
      const dca = Number(monthlyDca)
      if (!Number.isFinite(dca) || dca < 0) {
        toast({ title: 'Montant invalide', description: 'Le DCA mensuel doit être un montant positif ou nul.', variant: 'destructive' })
        return
      }
    }
    update.mutate({
      tmi_rate: tmiRate === '' ? null : Number(tmiRate),
      risk_profile: riskProfile === '' ? null : (riskProfile as RiskProfile),
      monthly_dca_eur: monthlyDca === '' ? null : Number(monthlyDca),
    })
  }

  return (
    <Card elevation="raised">
      <CardHeader>
        <div className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5" />
          <CardTitle>Profil investisseur</CardTitle>
        </div>
        <CardDescription>
          Vos paramètres financiers — utilisés par le dashboard, les suggestions et les simulateurs
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {profile.isError ? (
          <QueryErrorState
            error={profile.error}
            onRetry={profile.refetch}
            busy={profile.isFetching}
            title="Profil investisseur indisponible"
            description="Vos paramètres n'ont pas pu être chargés. Ils ne sont pas modifiables tant que la lecture n'a pas abouti, pour éviter de les écraser."
          />
        ) : (
          <>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="tmiRate">Tranche marginale d'imposition (TMI)</Label>
                <Select value={tmiRate} onValueChange={setTmiRate}>
                  <SelectTrigger id="tmiRate">
                    <SelectValue placeholder="Non renseignée" />
                  </SelectTrigger>
                  <SelectContent>
                    {TMI_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Utilisée par l'estimation d'impôt au barème progressif (dashboard)
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="riskProfile">Profil de risque</Label>
                <Select value={riskProfile} onValueChange={setRiskProfile}>
                  <SelectTrigger id="riskProfile">
                    <SelectValue placeholder="Non renseigné" />
                  </SelectTrigger>
                  <SelectContent>
                    {RISK_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">Utilisé par les suggestions de déploiement de capital</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="monthlyDca">DCA mensuel (€)</Label>
                <Input
                  id="monthlyDca"
                  type="number"
                  min={0}
                  step={50}
                  inputMode="decimal"
                  placeholder="ex : 500"
                  value={monthlyDca}
                  onChange={(e) => setMonthlyDca(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">Pré-remplit les simulateurs de projection</p>
              </div>
            </div>
            <Button onClick={save} disabled={update.isPending}>
              {update.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Enregistrer le profil investisseur
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  )
}
