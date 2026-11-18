import { useState, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { http } from '@/shared/api/http'
import { queryKeys } from '@/lib/queryKeys'
import { toast } from '@/hooks/use-toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Calculator, Loader2, Plus, X } from 'lucide-react'
import SimulationPreview from './SimulationPreview'
import {
  apiError,
  emptyForm,
  emptyRow,
  FREQUENCY_OPTIONS,
  TEMPLATE_OPTIONS,
  toParams,
  type Row,
  type Simulation,
  type SimulatorForm,
  type TemplateKind,
} from './simulatorModel'

const ROW_LABELS: Record<TemplateKind, { symbol: boolean; a: string; b?: string; add: string }> = {
  dca: { symbol: true, a: 'Part (%)', add: 'Ajouter un actif' },
  vca: { symbol: true, a: '', add: '' },
  profit_taking: { symbol: false, a: 'Prix de déclenchement (€)', b: 'Part à vendre (%)', add: 'Ajouter un palier' },
  rebalance: { symbol: true, a: 'Cible (%)', b: 'Valeur actuelle (€)', add: 'Ajouter un actif' },
}

function Field({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id} className="text-xs">
        {label}
      </Label>
      {children}
    </div>
  )
}

const today = () => new Date().toISOString().slice(0, 10)

export default function StrategySimulator({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<SimulatorForm>(() => emptyForm(today()))
  const [name, setName] = useState('')
  const [simulation, setSimulation] = useState<Simulation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const labels = ROW_LABELS[form.template]

  const update = (patch: Partial<SimulatorForm>) => {
    setForm((prev) => ({ ...prev, ...patch }))
    setSimulation(null)
    setError(null)
  }
  const updateRow = (idx: number, field: keyof Row, value: string) =>
    update({ rows: form.rows.map((r, i) => (i === idx ? { ...r, [field]: value } : r)) })

  const close = (next: boolean) => {
    onOpenChange(next)
    if (!next) {
      setForm(emptyForm(today()))
      setName('')
      setSimulation(null)
      setError(null)
    }
  }

  const simulate = useMutation({
    mutationFn: async () => {
      const body = { params: toParams(form), backtest_start: form.backtestStart || null }
      return (await http.post<Simulation>('/strategies/simulate', body)).data
    },
    onSuccess: (data) => setSimulation(data),
    onError: (e) => setError(apiError(e)),
  })

  const save = useMutation({
    mutationFn: async () =>
      (await http.post('/strategies/from-template', { name: name.trim(), params: toParams(form) })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.strategies.all })
      toast({ title: 'Stratégie programmée', description: 'Son échéancier apparaît dans vos stratégies actives.' })
      close(false)
    },
    onError: (e) => setError(apiError(e)),
  })

  const hint = TEMPLATE_OPTIONS.find((t) => t.value === form.template)?.hint
  const scheduled = form.template !== 'profit_taking'

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Simulateur de stratégies</DialogTitle>
        </DialogHeader>
        <div className="space-y-5 py-2">
          <Field id="sim-template" label="Modèle">
            <Select
              value={form.template}
              onValueChange={(v) => update({ template: v as TemplateKind, rows: [emptyRow()], symbol: '', amount: '' })}
            >
              <SelectTrigger id="sim-template" aria-label="Modèle">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TEMPLATE_OPTIONS.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">{hint}</p>
          </Field>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {(form.template === 'vca' || form.template === 'profit_taking') && (
              <Field id="sim-symbol" label="Actif">
                <Input id="sim-symbol" value={form.symbol} onChange={(e) => update({ symbol: e.target.value.toUpperCase() })} placeholder="Symbole" />
              </Field>
            )}
            {form.template === 'dca' && (
              <Field id="sim-amount" label="Budget par échéance (€)">
                <Input id="sim-amount" inputMode="decimal" value={form.amount} onChange={(e) => update({ amount: e.target.value })} placeholder="Montant choisi" />
              </Field>
            )}
            {form.template === 'vca' && (
              <>
                <Field id="sim-amount" label="Hausse de la valeur visée par échéance (€)">
                  <Input id="sim-amount" inputMode="decimal" value={form.amount} onChange={(e) => update({ amount: e.target.value })} placeholder="Montant choisi" />
                </Field>
                <Field id="sim-max" label="Plafond par échéance (€, facultatif)">
                  <Input id="sim-max" inputMode="decimal" value={form.maxPerPeriod} onChange={(e) => update({ maxPerPeriod: e.target.value })} />
                </Field>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={form.allowSell} onChange={(e) => update({ allowSell: e.target.checked })} />
                  Vendre l’excédent quand la ligne dépasse la cible
                </label>
              </>
            )}
            {form.template === 'profit_taking' && (
              <Field id="sim-quantity" label="Quantité concernée">
                <Input id="sim-quantity" inputMode="decimal" value={form.quantity} onChange={(e) => update({ quantity: e.target.value })} placeholder="Quantité choisie" />
              </Field>
            )}
            {form.template === 'rebalance' && (
              <>
                <Field id="sim-contribution" label="Apport à répartir (€, facultatif)">
                  <Input id="sim-contribution" inputMode="decimal" value={form.contribution} onChange={(e) => update({ contribution: e.target.value })} />
                </Field>
                <Field id="sim-threshold" label="Seuil d’écart avant d’agir (points, facultatif)">
                  <Input id="sim-threshold" inputMode="decimal" value={form.threshold} onChange={(e) => update({ threshold: e.target.value })} />
                </Field>
              </>
            )}
          </div>

          {form.template !== 'vca' && (
            <div className="space-y-2">
              {form.rows.map((row, idx) => (
                <div key={idx} className="flex items-end gap-2">
                  {labels.symbol && (
                    <Field id={`sim-row-symbol-${idx}`} label={`Actif ${idx + 1}`}>
                      <Input id={`sim-row-symbol-${idx}`} value={row.symbol} onChange={(e) => updateRow(idx, 'symbol', e.target.value.toUpperCase())} placeholder="Symbole" />
                    </Field>
                  )}
                  <Field id={`sim-row-a-${idx}`} label={`${labels.a} ${idx + 1}`}>
                    <Input id={`sim-row-a-${idx}`} inputMode="decimal" value={row.a} onChange={(e) => updateRow(idx, 'a', e.target.value)} />
                  </Field>
                  {labels.b && (
                    <Field id={`sim-row-b-${idx}`} label={`${labels.b} ${idx + 1}`}>
                      <Input id={`sim-row-b-${idx}`} inputMode="decimal" value={row.b} onChange={(e) => updateRow(idx, 'b', e.target.value)} />
                    </Field>
                  )}
                  {form.rows.length > 1 && (
                    <Button type="button" variant="ghost" size="sm" aria-label={`Retirer la ligne ${idx + 1}`} onClick={() => update({ rows: form.rows.filter((_, i) => i !== idx) })}>
                      <X className="h-3 w-3" />
                    </Button>
                  )}
                </div>
              ))}
              <Button type="button" variant="outline" size="sm" onClick={() => update({ rows: [...form.rows, emptyRow()] })}>
                <Plus className="h-3 w-3 mr-1" />
                {labels.add}
              </Button>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {scheduled && (
              <>
                <Field id="sim-frequency" label="Fréquence">
                  <Select value={form.frequency} onValueChange={(v) => update({ frequency: v as SimulatorForm['frequency'] })}>
                    <SelectTrigger id="sim-frequency" aria-label="Fréquence">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {FREQUENCY_OPTIONS.map((f) => (
                        <SelectItem key={f.value} value={f.value}>
                          {f.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <Field id="sim-periods" label="Nombre d’échéances">
                  <Input id="sim-periods" inputMode="numeric" value={form.periods} onChange={(e) => update({ periods: e.target.value })} />
                </Field>
                <Field id="sim-start" label="Première échéance">
                  <Input id="sim-start" type="date" value={form.startDate} onChange={(e) => update({ startDate: e.target.value })} />
                </Field>
              </>
            )}
            <Field id="sim-backtest" label="Simuler sur l’historique depuis (facultatif)">
              <Input id="sim-backtest" type="date" value={form.backtestStart} onChange={(e) => update({ backtestStart: e.target.value })} />
            </Field>
          </div>

          {error && (
            <p role="alert" className="text-sm text-loss">
              {error}
            </p>
          )}
          {simulation && <SimulationPreview simulation={simulation} />}
          {simulation && (
            <Field id="sim-name" label="Nom de la stratégie">
              <Input id="sim-name" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)}>
            Annuler
          </Button>
          <Button variant={simulation ? 'outline' : 'default'} onClick={() => simulate.mutate()} disabled={simulate.isPending}>
            {simulate.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Calculator className="h-4 w-4 mr-2" />}
            Calculer l’aperçu
          </Button>
          {simulation && (
            <Button onClick={() => save.mutate()} disabled={!name.trim() || save.isPending}>
              {save.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Enregistrer la stratégie
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
