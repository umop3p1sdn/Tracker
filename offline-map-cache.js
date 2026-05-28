// ═══════════════════════════════════════════════════════════════
// OFFLINE MAP TILE CACHING (V2.32)
// Pre-cache 50km radius around Ede + auto-cache on zoom/pan
// ═══════════════════════════════════════════════════════════════

// Ede coordinates (center point)
const EDE_LAT = 52.04;
const EDE_LNG = 5.67;
const CACHE_RADIUS_KM = 50;

// Tile URL template
const TILE_URL_TEMPLATE = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_SERVERS = ['a', 'b', 'c'];

// Convert lat/lng to tile coordinates
function latlngToTile(lat, lng, zoom) {
  const n = Math.pow(2, zoom);
  const x = Math.floor(n * ((lng + 180) / 360));
  const y = Math.floor(n * ((1 - Math.log(Math.tan(lat * Math.PI / 180) + 1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2));
  return { x, y, z: zoom };
}

// Convert tile to lat/lng bounds
function tileToBounds(x, y, zoom) {
  const n = Math.pow(2, zoom);
  const lng1 = (x / n) * 360 - 180;
  const lng2 = ((x + 1) / n) * 360 - 180;
  const lat1 = Math.atan(Math.sinh(Math.PI * (1 - 2 * (y + 1) / n))) * 180 / Math.PI;
  const lat2 = Math.atan(Math.sinh(Math.PI * (1 - 2 * y / n))) * 180 / Math.PI;
  return { n: lat2, s: lat1, e: lng2, w: lng1 };
}

// Calculate approximate tiles needed for radius
function getTilesForRadius(centerLat, centerLng, radiusKm, zoom) {
  const tiles = [];
  const radiusInDegrees = radiusKm / 111; // ~111km per degree
  
  const minLat = centerLat - radiusInDegrees;
  const maxLat = centerLat + radiusInDegrees;
  const minLng = centerLng - radiusInDegrees;
  const maxLng = centerLng + radiusInDegrees;
  
  // Get corner tiles
  const nwTile = latlngToTile(maxLat, minLng, zoom);
  const seTile = latlngToTile(minLat, maxLng, zoom);
  
  // Generate all tiles in rectangle
  for (let x = nwTile.x; x <= seTile.x; x++) {
    for (let y = nwTile.y; y <= seTile.y; y++) {
      tiles.push({ x, y, z: zoom });
    }
  }
  
  return tiles;
}

// Generate tile URLs from tile coordinates
function generateTileUrls(tiles) {
  const urls = [];
  tiles.forEach(tile => {
    TILE_SERVERS.forEach((server, idx) => {
      const url = TILE_URL_TEMPLATE
        .replace('{s}', server)
        .replace('{z}', tile.z)
        .replace('{x}', tile.x)
        .replace('{y}', tile.y);
      urls.push(url);
    });
  });
  return urls;
}

// Request Service Worker to pre-cache tiles
function preCacheTiles(tiles) {
  if (navigator.serviceWorker && navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({
      type: 'PRE_CACHE_TILES',
      tiles: tiles
    });
    console.log(`📍 Requested to cache ${tiles.length} tiles`);
  }
}

// Initialize offline map caching
function initOfflineMapCaching() {
  console.log('🗺️ Initializing offline map caching...');
  
  // Pre-cache zoom levels 10-13 for 50km radius
  const zoomLevels = [10, 11, 12, 13];
  let totalTiles = 0;
  const allTiles = [];
  
  zoomLevels.forEach(zoom => {
    const tiles = getTilesForRadius(EDE_LAT, EDE_LNG, CACHE_RADIUS_KM, zoom);
    allTiles.push(...tiles);
    totalTiles += tiles.length;
    console.log(`  Zoom ${zoom}: ${tiles.length} tiles`);
  });
  
  // Convert to URLs
  const tileUrls = generateTileUrls(allTiles);
  console.log(`📦 Total tiles to cache: ${totalTiles} (URLs: ${tileUrls.length})`);
  
  // Request caching (don't wait for it to complete)
  preCacheTiles(tileUrls);
  
  // Show status in console
  console.log(`✅ Offline caching initialized for ${CACHE_RADIUS_KM}km radius around Ede`);
  console.log(`   Tiles will be cached as you view them (zoom 14-15)`);
}

// Hook into map for auto-caching
function setupAutoTileCaching(mapInstance) {
  if (!mapInstance || !navigator.serviceWorker) return;
  
  // Cache tiles when user zooms/pans
  mapInstance.on('moveend zoomend', () => {
    const bounds = mapInstance.getBounds();
    const zoom = mapInstance.getZoom();
    
    // Only auto-cache zoom 14-15 (high detail, smaller area)
    if (zoom >= 14 && zoom <= 15) {
      const minTile = latlngToTile(bounds.getNorth(), bounds.getWest(), zoom);
      const maxTile = latlngToTile(bounds.getSouth(), bounds.getEast(), zoom);
      
      const tilesToCache = [];
      for (let x = minTile.x; x <= maxTile.x; x++) {
        for (let y = minTile.y; y <= maxTile.y; y++) {
          tilesToCache.push({ x, y, z: zoom });
        }
      }
      
      if (tilesToCache.length > 0 && tilesToCache.length < 100) {
        const urls = generateTileUrls(tilesToCache);
        preCacheTiles(urls);
      }
    }
  });
}

// Export functions for use in main app
window.OfflineMapCache = {
  init: initOfflineMapCaching,
  setupAutoCache: setupAutoTileCaching,
  getTilesForRadius: getTilesForRadius,
  generateTileUrls: generateTileUrls
};
