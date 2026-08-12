const CACHE_NAME = 'telugu-panchangam-v1'

self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)

  // Cache-first: geocoding (cities don't move)
  if (url.pathname.startsWith('/api/geocode')) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        return cached || fetch(event.request).then((response) => {
          const clone = response.clone()
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, clone)
          })
          return response
        })
      })
    )
    return
  }

  // Network-first with cache fallback: panchangam + festivals
  if (url.pathname.startsWith('/api/panchangam') ||
      url.pathname.startsWith('/api/festivals')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const clone = response.clone()
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, clone)
          })
          return response
        })
        .catch(() => caches.match(event.request))
    )
    return
  }

  // Default: network only (reminders, muhurtam, nakshatra)
  event.respondWith(fetch(event.request))
})
