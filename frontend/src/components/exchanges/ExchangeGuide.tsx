import { Fragment, type ReactNode } from 'react'
import {
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { CheckCircle, Copy, ExternalLink, Plus, ShieldCheck, XCircle } from 'lucide-react'
import type { ExchangeGuideData } from './exchange-guides'

/** Rend les segments **gras** d'un texte de guide en <strong>. */
const BoldText = ({ text }: { text: string }) => (
  <>
    {text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith('**') && part.endsWith('**') ? (
        <strong key={i}>{part.slice(2, -2)}</strong>
      ) : (
        <Fragment key={i}>{part}</Fragment>
      ),
    )}
  </>
)

interface ExchangeGuideProps {
  guide: ExchangeGuideData
  /** Logo de l'exchange affiché dans le titre (fourni par la page). */
  logo?: ReactNode
  onClose: () => void
  onConnect: () => void
}

/**
 * Guide de création de clé API pour un exchange, rendu depuis la structure
 * de données `ExchangeGuideData` (voir exchange-guides.ts). S'affiche dans
 * le corps d'un <DialogContent> : encadré « lecture seule », étapes
 * numérotées, permissions à cocher / interdites, clés à copier.
 */
export default function ExchangeGuide({ guide, logo, onClose, onConnect }: ExchangeGuideProps) {
  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-3">
          {logo}
          Créer une clé API sur {guide.name}
        </DialogTitle>
        <DialogDescription>
          Suivez ces étapes pour générer une clé API en lecture seule.
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-6 py-4">
        <div className="rounded-lg border border-warning/30 bg-warning/5 p-4">
          <div className="flex items-start gap-3">
            <ShieldCheck className="h-5 w-5 text-warning mt-0.5 shrink-0" />
            <div className="text-sm">
              <p className="font-medium text-warning dark:text-warning">Important : lecture seule</p>
              <p className="text-muted-foreground mt-1">
                <BoldText text={guide.readOnlyWarning} />
              </p>
            </div>
          </div>
        </div>

        <ol className="space-y-5">
          {guide.steps.map((step, stepIndex) => (
            <li key={step.title} className="flex gap-4">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">
                {stepIndex + 1}
              </span>
              <div>
                <p className="font-medium">{step.title}</p>
                {step.link && (
                  <p className="text-sm text-muted-foreground mt-1">
                    Rendez-vous sur{' '}
                    <a
                      href={step.link.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary underline inline-flex items-center gap-1"
                    >
                      {step.link.label} <ExternalLink className="h-3 w-3" />
                    </a>
                  </p>
                )}
                {step.details.map((detail, detailIndex) => (
                  <p
                    key={detail}
                    className={`text-sm text-muted-foreground${detailIndex === 0 && !step.link ? ' mt-1' : ''}`}
                  >
                    <BoldText text={detail} />
                  </p>
                ))}
                {step.permissionsChecked && (
                  <div className="mt-2 space-y-1.5">
                    {step.permissionsChecked.map((permission) => (
                      <div key={permission} className="flex items-center gap-2 text-sm">
                        <CheckCircle className="h-4 w-4 text-gain" />
                        <span>
                          <BoldText text={permission} />
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {step.permissionsForbidden && (
                  <div className="mt-2 space-y-1.5">
                    <p className="text-sm text-muted-foreground">
                      Ne cochez <strong>PAS</strong> :
                    </p>
                    {step.permissionsForbidden.map((permission) => (
                      <div key={permission} className="flex items-center gap-2 text-sm">
                        <XCircle className="h-4 w-4 text-loss" />
                        <span className="text-muted-foreground">{permission}</span>
                      </div>
                    ))}
                  </div>
                )}
                {step.keys && (
                  <div className="mt-2 space-y-2">
                    {step.keys.map((key) => (
                      <div
                        key={key.name}
                        className="flex items-center gap-2 text-sm bg-muted rounded-md p-2"
                      >
                        <Copy className="h-4 w-4 text-muted-foreground shrink-0" />
                        <div>
                          <span className="font-medium">{key.name}</span>
                          <span className="text-muted-foreground">
                            {' '}— à coller dans le champ "{key.field}"
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {step.warning && (
                  <p className="text-sm text-loss mt-2 font-medium">{step.warning}</p>
                )}
              </div>
            </li>
          ))}
        </ol>

        {guide.notes && guide.notes.length > 0 && (
          <ul className="space-y-1 text-sm text-muted-foreground">
            {guide.notes.map((note) => (
              <li key={note}>
                <BoldText text={note} />
              </li>
            ))}
          </ul>
        )}
      </div>
      <DialogFooter className="flex-col sm:flex-row gap-2">
        <Button variant="outline" onClick={onClose}>
          Fermer
        </Button>
        <Button onClick={onConnect}>
          <Plus className="h-4 w-4 mr-2" />
          Connecter {guide.name}
        </Button>
      </DialogFooter>
    </>
  )
}
