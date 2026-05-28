const CACHE_NAME = 'live-tracker-v2.32';
const TILE_DB_NAME = 'LiveTrackerTiles';
const TILE_STORE_NAME = 'tiles';

const urlsToCache = [
  '/tracker/',
  '/tracker/index.html',
  '/tracker/manifest.json'
];

// ═══════════════════════════════════════════════════════════════
// SIMPLE INDEXEDDB TILE CACHING
// ═══════════════════════════════════════════════════════════════

function openTileDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(TILE_DB_NAME, 1);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(TILE_STORE_NAME)) {
        db.createObjectStore(TILE_STORE_NAME, { keyPath: 'url' });
      }
    };
  });
}

function cacheTile(url, blob) {
  openTileDB().then(db => {
    const tx = db.transaction([TILE_STORE_NAME], 'readwrite');
    const store = tx.objectStore(TILE_STORE_NAME);
    store.put({ url: url, blob: blob, time: Date.now() });
  }).catch(() => {});
}

function getCachedTile(url) {
  return openTileDB().then(db => {
    return new Promise((resolve) => {
      const tx = db.transaction([TILE_STORE_NAME], 'readonly');
      const store = tx.objectStore(TILE_STORE_NAME);
      const req = store.get(url);
      req.onsuccess = () => resolve(req.result ? req.result.blob : null);
      req.onerror = () => resolve(null);
    });
  }).catch(() => Promise.resolve(null));
}

// ═══════════════════════════════════════════════════════════════

// Install
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(urlsToCache).catch(() => {});
    })
  );
  self.skipWaiting();
});

// Activate
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

// PRE-CACHE MESSAGE HANDLER
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'PRECACHE_TILES') {
    const tiles = event.data.tiles;
    console.log(`📦 Pre-caching ${tiles.length} tiles in background...`);
    tiles.forEach(tileUrl => {
      fetch(tileUrl)
        .then(r => r && r.status === 200 ? r.blob().then(b => cacheTile(tileUrl, b)) : null)
        .catch(() => {});
    });
  }
});

// Fetch - CORE LOGIC
self.addEventListener('fetch', (event) => {
  const url = event.request.url;
  
  // Skip non-GET and external APIs
  if (event.request.method !== 'GET' || 
      url.includes('firebase') || 
      url.includes('googleapis')) {
    return;
  }

  // OPENSTREETMAP TILES - AUTO CACHE
  if (url.includes('tile.openstreetmap.org') || url.includes('tile.osm.org')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          // Save tile while online
          if (response && response.status === 200) {
            const blob = response.clone().blob();
            blob.then(b => cacheTile(url, b));
          }
          return response;
        })
        .catch(() => {
          // Offline: use cached tile
          return getCachedTile(url).then(blob => {
            if (blob) {
              return new Response(blob, {
                status: 200,
                headers: { 'Content-Type': 'image/png' }
              });
            }
            // No cache: gray tile
            const canvas = new OffscreenCanvas(256, 256);
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#e0e0e0';
            ctx.fillRect(0, 0, 256, 256);
            return canvas.convertToBlob().then(grayBlob => 
              new Response(grayBlob, {
                status: 200,
                headers: { 'Content-Type': 'image/png' }
              })
            );
          });
        })
    );
    return;
  }

  // STANDARD FETCH - cache app files
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response && response.status === 200) {
          const responseToCache = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return response;
      })
      .catch(() => {
        return caches.match(event.request).then((response) => {
          return response || new Response('Offline', {
            status: 503,
            statusText: 'Service Unavailable'
          });
        });
      })
  );
});
