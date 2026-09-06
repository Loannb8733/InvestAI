/**
 * Affichage d'un solde crypto, dont l'ordre de grandeur varie de 10⁻⁸ à 10⁶.
 *
 * Un format unique ne convient pas : quatre décimales noieraient un solde de
 * poussière dans des zéros, et six sur un solde à six chiffres seraient
 * illisibles. La précision suit donc la grandeur.
 */
export function formatBalance(amount: number): string {
  if (amount === 0) return '0'
  if (amount < 0.00001) return amount.toExponential(2)
  if (amount < 1) return amount.toFixed(6)
  if (amount < 1000) return amount.toFixed(4)
  return amount.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
}
