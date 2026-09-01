import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

/**
 * EPIC G — garde-fous d'accessibilité.
 *
 * Ces contrôles sont statiques parce que ce qu'ils protègent est déclaratif :
 * un bouton icône sans nom accessible, une couleur sous le seuil de contraste,
 * un `group-hover` sans `group-focus-within`. Les vérifier au rendu
 * demanderait de monter chaque page ; les vérifier ici les couvre toutes, y
 * compris celles écrites après ce test.
 *
 * Ils ne remplacent pas un audit au lecteur d'écran (VERIF-01).
 */

const SRC = resolve(process.cwd(), 'src')

function fichiers(ext: RegExp, dir = SRC, acc: string[] = []): string[] {
  for (const e of readdirSync(dir)) {
    const p = join(dir, e)
    if (statSync(p).isDirectory()) fichiers(ext, p, acc)
    else if (ext.test(e) && !/\.test\.tsx?$/.test(e)) acc.push(p)
  }
  return acc
}

/** Fin de la balise ouvrante, en ignorant les `>` des expressions JSX et des `=>`. */
function finBaliseOuvrante(src: string, debut: number): number {
  let profondeur = 0
  for (let i = debut; i < src.length; i++) {
    const c = src[i]
    if (c === '{') profondeur++
    else if (c === '}') profondeur--
    else if (c === '>' && profondeur === 0 && src[i - 1] !== '=') return i
  }
  return -1
}

describe('A11Y-01 — tout bouton icône a un nom accessible', () => {
  it('aucun <Button size="icon"> sans aria-label, title, sr-only ou texte visible', () => {
    const muets: string[] = []

    for (const f of fichiers(/\.tsx$/)) {
      const src = readFileSync(f, 'utf-8')
      for (const m of src.matchAll(/<Button\b/g)) {
        const debut = m.index!
        const fin = finBaliseOuvrante(src, debut)
        const fermeture = src.indexOf('</Button>', debut)
        if (fin === -1 || fermeture === -1) continue

        const attributs = src.slice(debut, fin)
        if (!attributs.includes('size="icon"')) continue

        const contenu = src.slice(fin + 1, fermeture)
        const nomme = /aria-label|aria-labelledby|title=/.test(attributs) || contenu.includes('sr-only')
        // Texte visible : ce qui reste hors balises et hors expressions JS.
        const texte = contenu.replace(/<[^>]*>/g, '').replace(/\{[^}]*\}/g, '').trim()

        if (!nomme && !texte) {
          muets.push(`${f.replace(SRC, 'src')}:${src.slice(0, debut).split('\n').length}`)
        }
      }
    }

    expect(muets, 'bouton icône annoncé « bouton » et rien d\'autre').toEqual([])
  })
})

describe('A11Y-02 — les animations JS respectent prefers-reduced-motion', () => {
  it('MotionConfig reducedMotion="user" enveloppe l\'application', () => {
    // La media query CSS ne neutralise que les animations/transitions CSS.
    // framer-motion pilote ses valeurs en JS : sans ce garde global, chaque
    // composant devrait se protéger lui-même, et le prochain oubli passerait.
    const app = readFileSync(join(SRC, 'App.tsx'), 'utf-8')
    expect(app).toMatch(/<MotionConfig\s+reducedMotion="user">/)
  })
})

describe('A11Y-03 — le rail est utilisable au clavier', () => {
  /**
   * Source du NavRail, commentaires retirés.
   *
   * Les commentaires citent les classes qu'ils expliquent : chercher dans le
   * fichier brut ferait passer le test alors que la classe a disparu du
   * `className`. Vérifié par canari — sans ce filtrage, retirer
   * `focus-within:w-64` du composant laissait les 11 tests au vert.
   */
  const rail = () =>
    readFileSync(join(SRC, 'components/layout/NavRail.tsx'), 'utf-8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/^\s*\/\/.*$/gm, '')

  it('les libellés apparaissent aussi au focus, pas seulement au survol', () => {
    const src = rail()
    const survol = src.includes('group-hover:opacity-100')
    const focus = src.includes('group-focus-within:opacity-100')
    expect(survol && !focus, 'libellés révélés au survol seul : invisibles à la tabulation').toBe(false)
  })

  it('le rail s\'élargit aussi au focus, sinon les libellés sont tronqués', () => {
    // Révéler les libellés ne suffit pas : sans l'élargissement, ils s'affichent
    // dans un rail resté à 76 px et « Crowdfunding » devient « CROW ». Constaté
    // à l'écran après coup — aucune assertion sur le DOM ne voit une largeur CSS.
    const src = rail()
    const survol = src.includes('hover:w-64')
    const focus = src.includes('focus-within:w-64')
    expect(survol && !focus, 'rail élargi au survol seul : libellés tronqués au clavier').toBe(false)
  })
})

describe('A11Y-04 — contrastes conformes au seuil AA', () => {
  /** OKLCH → sRGB (même conversion que les navigateurs). */
  function srgb(L: number, C: number, H: number): [number, number, number] {
    const h = (H * Math.PI) / 180
    const a = C * Math.cos(h)
    const b = C * Math.sin(h)
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
    const lin = [
      4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
    ]
    return lin.map((x) => {
      const v = Math.max(0, Math.min(1, x))
      return v > 0.0031308 ? 1.055 * v ** (1 / 2.4) - 0.055 : 12.92 * v
    }) as [number, number, number]
  }

  function luminance([r, g, b]: [number, number, number]): number {
    const lin = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
  }

  function contraste(a: [number, number, number], b: [number, number, number]): number {
    const [l1, l2] = [luminance(srgb(...a)), luminance(srgb(...b))]
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)
  }

  /** Lit un token OKLCH dans le bloc `:root` (clair) ou `.dark` (sombre). */
  function token(nom: string, theme: 'clair' | 'sombre'): [number, number, number] {
    const css = readFileSync(join(SRC, 'index.css'), 'utf-8')
    const debut = theme === 'clair' ? css.indexOf(':root {') : css.indexOf('.dark {')
    const fin = theme === 'clair' ? css.indexOf('.dark {') : css.length
    const bloc = css.slice(debut, fin === -1 ? css.length : fin)
    const m = bloc.match(new RegExp(`--${nom}:\\s*([\\d.]+)\\s+([\\d.]+)\\s+([\\d.]+)`))
    if (!m) throw new Error(`token --${nom} introuvable dans le thème ${theme}`)
    return [Number(m[1]), Number(m[2]), Number(m[3])]
  }

  it.each([
    ['gain', 'clair'],
    ['loss', 'clair'],
    ['gain', 'sombre'],
    ['loss', 'sombre'],
    ['muted-foreground', 'clair'],
    ['muted-foreground', 'sombre'],
  ] as const)('--%s (%s) atteint 4.5:1 sur fond et sur carte', (nom, theme) => {
    // gain et loss portent les montants de plus-value : ce sont des chiffres
    // qu'on lit, pas de la décoration — le seuil du texte normal s'applique.
    for (const fond of ['background', 'card'] as const) {
      expect(contraste(token(nom, theme), token(fond, theme))).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('aucun texte en muted-foreground atténué par une opacité', () => {
    // `/70` faisait tomber le libellé à 3,07:1 en clair et 3,84:1 en sombre.
    const coupables = fichiers(/\.tsx$/).filter((f) =>
      /text-muted-foreground\/\d+/.test(readFileSync(f, 'utf-8'))
    )
    expect(coupables.map((f) => f.replace(SRC, 'src'))).toEqual([])
  })
})
