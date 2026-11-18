import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ASSET_TYPES, canCreateAsset, isRealEstate, type AssetDraft } from '../assetDraft'
import PlatformSelect from './PlatformSelect'

interface NewAssetPanelProps {
  draft: AssetDraft
  onChange: (draft: AssetDraft) => void
  pending: boolean
  onCreate: () => void
  onCancel: () => void
}

function TextField({ label, value, onChange, ...input }: { label: string; value: string; onChange: (v: string) => void; type?: string; step?: string; placeholder?: string }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Input value={value} onChange={(e) => onChange(e.target.value)} {...input} />
    </div>
  )
}

export default function NewAssetPanel({ draft, onChange, pending, onCreate, onCancel }: NewAssetPanelProps) {
  const set = (field: keyof AssetDraft) => (value: string) => onChange({ ...draft, [field]: value })
  return (
    <div className="space-y-3 rounded-lg border border-border bg-muted/20 p-3">
      <div className="flex items-center justify-between">
        <Label className="font-medium">Nouvel actif</Label>
        <Button type="button" variant="ghost" size="sm" className="h-auto py-0 px-1 text-xs" onClick={onCancel}>
          Annuler
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">Type *</Label>
          <Select value={draft.type} onValueChange={set('type')}>
            <SelectTrigger aria-label="Type d'actif">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ASSET_TYPES.map((t) => (
                <SelectItem key={t.value} value={t.value}>
                  {t.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Plateforme *</Label>
          <PlatformSelect value={draft.exchange} onChange={set('exchange')} placeholder="Plateforme..." showTrustBadge />
        </div>
      </div>
      {isRealEstate(draft) ? (
        <>
          <TextField label="Nom du projet *" placeholder="Résidence Lyon Centre..." value={draft.name} onChange={set('name')} />
          <div className="grid grid-cols-3 gap-2">
            <TextField label="Montant investi *" type="number" placeholder="2000" value={draft.invested} onChange={set('invested')} />
            <TextField label="Taux annuel (%)" type="number" step="0.1" placeholder="10.5" value={draft.rate} onChange={set('rate')} />
            <TextField label="Echéance" type="date" value={draft.maturity} onChange={set('maturity')} />
          </div>
        </>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <TextField label="Symbole *" placeholder="BTC, AAPL..." value={draft.symbol} onChange={set('symbol')} />
          <TextField label="Nom" placeholder="Bitcoin, Apple..." value={draft.name} onChange={set('name')} />
        </div>
      )}
      <Button type="button" size="sm" className="w-full" disabled={!canCreateAsset(draft) || pending} onClick={onCreate}>
        {pending && <Loader2 className="mr-2 h-3 w-3 animate-spin" />}
        Créer l&apos;actif
      </Button>
    </div>
  )
}
