// Nom de cache versionné : le changer purge l'ancien à l'activation.
// v2 : la page d'entrée n'est plus servie « cache d'abord ».
const CACHE_NAME = 'investai-v2'
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/icons/icon-192.svg',
  '/icons/icon-512.svg',
]

// Install: cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  )
  self.skipWaiting()
})

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  )
  self.clients.claim()
})

// Mémorise une réponse sans jamais faire échouer la requête : `cache.put`
// rejette sur une réponse partielle (206) ou une requête d'extension, et une
// promesse non rattrapée finissait en « Uncaught (in promise) TypeError:
// Failed to execute 'put' on 'Cache' » dans la console.
function memoriser(request, response) {
  if (!response.ok || request.method !== 'GET') return
  const clone = response.clone()
  caches
    .open(CACHE_NAME)
    .then((cache) => cache.put(request, clone))
    .catch(() => {})
}

// Fetch: réseau d'abord pour la page, cache d'abord pour les fichiers hachés,
// cache puis rafraîchissement pour le reste.
self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  // Never cache API calls
  if (url.pathname.startsWith('/api')) return
  // Seul http(s) se met en cache : une requête d'extension ferait échouer put.
  if (!url.protocol.startsWith('http')) return

  // La page d'entrée (index.html) porte les noms hachés des scripts du
  // déploiement courant. La servir « cache d'abord » montrait la version
  // précédente à chaque premier chargement après un déploiement — la
  // nouvelle n'apparaissait qu'au chargement suivant. Réseau d'abord ; le
  // cache ne sert que hors ligne.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          memoriser(request, response)
          return response
        })
        .catch(() => caches.match(request))
    )
    return
  }

  // Un fichier haché (/assets/App-abc123.js) ne change jamais de contenu :
  // le cache suffit, le réseau n'est consulté qu'à son absence.
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            memoriser(request, response)
            return response
          })
      )
    )
    return
  }

  // Manifeste, icônes : cache tout de suite, rafraîchi en arrière-plan.
  event.respondWith(
    caches.match(request).then((cached) => {
      const fetchPromise = fetch(request)
        .then((response) => {
          memoriser(request, response)
          return response
        })
        .catch(() => cached)

      return cached || fetchPromise
    })
  )
})
