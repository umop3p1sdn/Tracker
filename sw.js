const CACHE_NAME = 'live-tracker-v2.2';
const urlsToCache = [
  '/tracker/',
  '/tracker/index.html',
  '/tracker/manifest.json',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet-plugins/1.2.2/rotatedMarker.min.js'
];

// Install event
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll([
        '/tracker/',
        '/tracker/index.html',
        '/tracker/manifest.json'
      ]).catch(() => {
        // Offline: cache what we can
        console.log('Some resources could not be cached');
      });
    })
  );
  self.skipWaiting();
});

// Activate event
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// ═══════════════════════════════════════════════════════════════
// V2.32: OFFLINE TILE CACHING (IndexedDB)
// ═══════════════════════════════════════════════════════════════
const TILE_DB_NAME = 'LiveTrackerTiles';
const TILE_STORE_NAME = 'tiles';
const MAX_TILE_CACHE_MB = 100;

function initTileDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(TILE_DB_NAME, 1);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(TILE_STORE_NAME)) {
        const store = db.createObjectStore(TILE_STORE_NAME, { keyPath: 'url' });
        store.createIndex('timestamp', 'timestamp', { unique: false });
      }
    };
  });
}

function saveTile(url, blob) {
  return initTileDB().then(db => {
    return new Promise((resolve) => {
      const transaction = db.transaction([TILE_STORE_NAME], 'readwrite');
      const store = transaction.objectStore(TILE_STORE_NAME);
      const tile = { url: url, blob: blob, size: blob.size, timestamp: Date.now() };
      store.put(tile);
      resolve(tile);
    });
  }).catch(() => {});
}

function getTile(url) {
  return initTileDB().then(db => {
    return new Promise((resolve) => {
      const transaction = db.transaction([TILE_STORE_NAME], 'readonly');
      const store = transaction.objectStore(TILE_STORE_NAME);
      const request = store.get(url);
      request.onsuccess = () => resolve(request.result ? request.result.blob : null);
      request.onerror = () => resolve(null);
    });
  }).catch(() => Promise.resolve(null));
}

// ═══════════════════════════════════════════════════════════════

// Fetch event - network first, fallback to cache
self.addEventListener('fetch', (event) => {
  const url = event.request.url;
  
  // Skip non-GET requests and external APIs
  if (event.request.method !== 'GET' || url.includes('firebase') || url.includes('googleapis')) {
    return;
  }

  // SPECIAL HANDLING: OpenStreetMap tiles (V2.32)
  if (url.includes('tile.openstreetmap.org') || url.includes('tile.osm.org')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response && response.status === 200) {
            response.clone().blob().then(blob => saveTile(url, blob));
          }
          return response;
        })
        .catch(() => {
          // Offline: try IndexedDB
          return getTile(url).then(blob => {
            if (blob) {
              return new Response(blob, {
                status: 200,
                headers: { 'Content-Type': 'image/png' }
              });
            }
            // Fallback: gray tile
            return new Response(new Uint8Array(100), {
              status: 200,
              headers: { 'Content-Type': 'image/png' }
            });
          });
        })
    );
    return;
  }

  // NORMAL HANDLING: everything else (existing code)

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Cache successful responses
        if (response && response.status === 200) {
          const responseToCache = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return response;
      })
      .catch(() => {
        // Offline: return cached version
        return caches.match(event.request).then((response) => {
          return response || new Response('Offline - page not cached', {
            status: 503,
            statusText: 'Service Unavailable',
            headers: new Headers({ 'Content-Type': 'text/plain' })
          });
        });
      })
  );
});
