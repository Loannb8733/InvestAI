import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'

/**
 * AuroraCanvas — fond vivant du design system.
 *
 * Nappes lumineuses aux teintes de la marque (violet / émeraude / cyan) qui
 * dérivent lentement derrière le contenu — la profondeur d'une salle de marché
 * la nuit, sans le coût d'un moteur 3D (canvas 2D pur, zéro dépendance).
 *
 * Sobriété technique :
 * - rAF throttlé ~30 fps (un fond n'a pas besoin de 60) ;
 * - pause totale quand l'onglet est caché (visibilitychange) ;
 * - `prefers-reduced-motion` → une seule frame statique, aucune boucle ;
 * - DPR plafonné à 1.5, resize via ResizeObserver ;
 * - `aria-hidden` : purement décoratif.
 */

interface AuroraCanvasProps {
  className?: string
  /** Opacité globale du voile (défaut 0.5 — présent sans gêner la lecture). */
  opacity?: number
}

// Nappes : hue OKLCH-approx portées en HSL canvas (violet, émeraude, cyan)
const BLOBS = [
  { h: 265, s: 85, l: 60, r: 0.55, speed: 0.00021, phase: 0 },
  { h: 160, s: 60, l: 45, r: 0.45, speed: 0.00016, phase: 2.1 },
  { h: 210, s: 70, l: 55, r: 0.5, speed: 0.00012, phase: 4.2 },
]

export default function AuroraCanvas({ className, opacity = 0.5 }: AuroraCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
    let raf = 0
    let last = 0
    let running = true

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = canvas
      canvas.width = Math.max(1, Math.round(w * dpr))
      canvas.height = Math.max(1, Math.round(h * dpr))
    }

    const paint = (t: number) => {
      const { width: w, height: h } = canvas
      ctx.clearRect(0, 0, w, h)
      ctx.globalCompositeOperation = 'lighter'
      for (const b of BLOBS) {
        const angle = t * b.speed + b.phase
        const cx = w * (0.5 + 0.32 * Math.cos(angle))
        const cy = h * (0.5 + 0.28 * Math.sin(angle * 1.3))
        const radius = Math.max(w, h) * b.r
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius)
        g.addColorStop(0, `hsla(${b.h}, ${b.s}%, ${b.l}%, 0.14)`)
        g.addColorStop(1, 'hsla(0, 0%, 0%, 0)')
        ctx.fillStyle = g
        ctx.fillRect(0, 0, w, h)
      }
      ctx.globalCompositeOperation = 'source-over'
    }

    const loop = (t: number) => {
      if (!running) return
      raf = requestAnimationFrame(loop)
      if (t - last < 33) return // ~30 fps suffit pour une dérive lente
      last = t
      paint(t)
    }

    const onVisibility = () => {
      running = !document.hidden && !reduced
      if (running) {
        raf = requestAnimationFrame(loop)
      } else {
        cancelAnimationFrame(raf)
      }
    }

    const observer = new ResizeObserver(() => {
      resize()
      if (reduced) paint(0)
    })
    observer.observe(canvas)
    resize()

    if (reduced) {
      paint(0) // une frame, puis silence
    } else {
      raf = requestAnimationFrame(loop)
      document.addEventListener('visibilitychange', onVisibility)
    }

    return () => {
      running = false
      cancelAnimationFrame(raf)
      observer.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      style={{ opacity }}
      className={cn('pointer-events-none absolute inset-0 h-full w-full', className)}
    />
  )
}
