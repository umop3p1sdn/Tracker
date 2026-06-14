const CACHE_NAME = 'live-tracker-tiles'; // Static - no version needed
const TILE_DB_NAME = 'LiveTrackerTiles';
const TILE_STORE_NAME = 'tiles';

// Gray 256x256 PNG placeholder for offline tiles not yet cached
// (avoids OffscreenCanvas, which older iOS Safari does not support)
const GRAY_TILE_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAIAAADTED8xAAAB+0lEQVR42u3TMQ0AAAzDsPJHWSi9h2E2hEhJ4bFIgAHAAGAAMAAYAAwABgADgAHAAGAAMAAYAAwABgADgAHAAGAAMAAYAAwABgADgAHAAGAAMAAYAAwABgADgAHAAGAAMAAYAAwABgADgAHAAGAAMAAYAAwABgADgAHAAGAADAAGAAOAAcAAYAAwABgADAAGAAOAAcAAYAAwABgADAAGAAOAAcAAYAAwABgADAAGAAOAAcAAYAAwABgADAAGAAOAAcAAYAAwABgADAAGAAOAAcAAYAAwABgADAAGAAOAATAAGAAMAAYAA4ABwABgADAAGAAMAAYAA4ABwABgADAAGAAMAAYAA4ABwABgADAAGAAMAAYAA4ABwABgADAAGAAMAAYAA4ABwABgADAAGAAMAAYAA4ABwABgADAAGAAMgAHAAGAAMAAYAAwABgADgAHAAGAAMAAYAAwABgADgAHAAGAAMAAYAAwABgADgAHAAGAAMAAYAAwABgADgAHAAGAAMAAYAAwABgADgAHAAGAAMAAYAAwABgADgAHAAGAAMAAGAAOAAcAAYAAwABgADAAGAAOAAcAAYAAwABgADAAGAAOAAcAAYAAwABgADAAGAAOAAcAAYAAwABgADAAGAAOAAcAAYAAwABgADAAGAAOAAcAAYAAwABgADADXACh2J2E5vNZJAAAAAElFTkSuQmCC';

const urlsToCache = [
  '/Tracker/',
  '/Tracker/index.html',
  '/Tracker/manifest.json'
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
  // Store as ArrayBuffer (raw bytes) - reliable on iOS Safari,
  // which is buggy storing Blobs directly in IndexedDB
  blob.arrayBuffer().then(buffer => {
    openTileDB().then(db => {
      const tx = db.transaction([TILE_STORE_NAME], 'readwrite');
      const store = tx.objectStore(TILE_STORE_NAME);
      store.put({ url: url, buffer: buffer, time: Date.now() });
    }).catch(() => {});
  }).catch(() => {});
}

function getCachedTile(url) {
  return openTileDB().then(db => {
    return new Promise((resolve) => {
      const tx = db.transaction([TILE_STORE_NAME], 'readonly');
      const store = tx.objectStore(TILE_STORE_NAME);
      const req = store.get(url);
      req.onsuccess = () => resolve(req.result ? req.result.buffer : null);
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
  // Tel hoeveel tegels er IN TOTAAL in de offline-opslag zitten (voor de teller in het menu).
  if (event.data && event.data.type === 'COUNT_TILES') {
    openTileDB().then(db => {
      const tx = db.transaction([TILE_STORE_NAME], 'readonly');
      const store = tx.objectStore(TILE_STORE_NAME);
      const req = store.count();
      req.onsuccess = () => {
        if (event.source) event.source.postMessage({ type: 'TILE_COUNT', count: req.result });
      };
      req.onerror = () => {
        if (event.source) event.source.postMessage({ type: 'TILE_COUNT', count: null });
      };
    }).catch(() => {
      if (event.source) event.source.postMessage({ type: 'TILE_COUNT', count: null });
    });
    return;
  }
  if (event.data && event.data.type === 'PRECACHE_TILES') {
    const tiles = event.data.tiles;
    console.log(`📦 Pre-caching ${tiles.length} tiles (throttled, skip cached)...`);

    const total = tiles.length;
    let downloaded = 0;
    const BATCH_SIZE = 5;     // tiles fetched in parallel per batch
    const BATCH_DELAY = 600;  // ms pause between batches (gentle on OSM)

    const sleep = (ms) => new Promise(res => setTimeout(res, ms));

    const processTile = (tileUrl) => {
      // Skip download if already cached - no request to OSM, saves data
      return getCachedTile(tileUrl).then(existing => {
        if (existing) return null;
        downloaded++;
        return fetch(tileUrl)
          .then(r => r && r.status === 200 ? r.blob().then(b => cacheTile(tileUrl, b)) : null)
          .catch(() => {});
      });
    };

    (async () => {
      for (let i = 0; i < tiles.length; i += BATCH_SIZE) {
        const batch = tiles.slice(i, i + BATCH_SIZE);
        const before = downloaded;
        await Promise.all(batch.map(processTile));
        // Only pause when this batch actually hit the network AND more remain.
        // Stationary (all cached) = no delays, instant + zero OSM load.
        if (downloaded > before && i + BATCH_SIZE < tiles.length) {
          await sleep(BATCH_DELAY);
        }
      }
      // All done - confirm to the page
      self.clients.matchAll({ includeUncontrolled: true }).then(clients => {
        clients.forEach(client => {
          client.postMessage({
            type: 'PRECACHE_COMPLETE',
            tilesCount: total,
            downloaded: downloaded
          });
        });
      });
    })();
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
          return getCachedTile(url).then(buffer => {
            if (buffer) {
              return new Response(buffer, {
                status: 200,
                headers: { 'Content-Type': 'image/png' }
              });
            }
            // No cache: gray placeholder (no OffscreenCanvas - works on all iOS)
            const bin = atob(GRAY_TILE_B64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
            return new Response(bytes, {
              status: 200,
              headers: { 'Content-Type': 'image/png' }
            });
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
