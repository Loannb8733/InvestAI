/**
 * Tokens live in CSS as raw OKLCH channels ("L C H"). Several chart libraries
 * (lightweight-charts' ColorParser, Nivo's d3-color based math) cannot parse
 * `oklch(...)` and either throw or compute wrong derived colors. Chromium also
 * keeps `getComputedStyle().color` in oklch form, so a DOM round-trip can't
 * normalize it. We therefore convert OKLCH → sRGB ourselves and hand libraries
 * an `rgb()/rgba()` string. Rendered color is identical, and dark/light/system
 * still track the same CSS source of truth.
 */
export function oklchToRgb(L: number, C: number, H: number): [number, number, number] {
  const h = (H * Math.PI) / 180
  const a = C * Math.cos(h)
  const b = C * Math.sin(h)

  const l_ = L + 0.3963377774 * a + 0.2158037573 * b
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b
  const s_ = L - 0.0894841775 * a - 1.291485548 * b

  const l = l_ * l_ * l_
  const m = m_ * m_ * m_
  const s = s_ * s_ * s_

  const lr = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
  const lg = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
  const lb = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s

  const gamma = (c: number) =>
    c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055

  const to255 = (c: number) => Math.round(Math.min(1, Math.max(0, gamma(c))) * 255)
  return [to255(lr), to255(lg), to255(lb)]
}

/** Resolve a CSS OKLCH-channel custom property to an `rgb()`/`rgba()` string. */
export function oklchVar(name: string, alpha?: number): string {
  const channels = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim()
  if (!channels) return alpha != null ? `rgba(0,0,0,${alpha})` : '#000'
  const [L, C, H] = channels.split(/\s+/).map(Number)
  if ([L, C, H].some((n) => Number.isNaN(n))) {
    return alpha != null ? `rgba(0,0,0,${alpha})` : '#000'
  }
  const [r, g, b] = oklchToRgb(L, C, H)
  return alpha != null ? `rgba(${r}, ${g}, ${b}, ${alpha})` : `rgb(${r}, ${g}, ${b})`
}
