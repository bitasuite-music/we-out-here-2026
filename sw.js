/* We Out Here 2026 — offline service worker.
 *
 * VER is the cache name. Bump it whenever index.html or either PDF changes,
 * or returning visitors keep the old files forever: the fetch handler below is
 * cache-first, so a stale hit is served before the network is even consulted,
 * and activate() only clears caches whose name differs from CACHE.
 *
 * Note that adding ?v=2 to a URL does NOT force a refresh here - the match
 * below uses ignoreSearch, so a query string is ignored and the old cached
 * entry is returned anyway. Bumping VER is the only thing that works.
 *
 * Strategy: cache-first, revalidate in the background. In a field with no
 * reception the app must open instantly and must never wait on a network
 * timeout, so the cached copy always wins. When there IS signal the fetch
 * still runs and refreshes the cache for next time.
 */
var VER = '8f9a021dff';  // built 2026-08-18
var CACHE = 'woh26-' + VER;

var ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icon-192.png',
  './icon-512.png',
  './apple-touch-icon.png',
  './icon-maskable-512.png',
  './melomaniacs-304.gif',
  './we-out-here-2026-set-times.pdf',
  './we-out-here-2026-set-times-2026-08-18.pdf',
  './we-out-here-2026-wider-programme.pdf',
  './we-out-here-2026-wider-programme-2026-08-18.pdf'
];

self.addEventListener('install', function (e) {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(function (c) {
    // Deliberately not cache.addAll: that rejects the whole install if a single
    // file 404s, which would leave people with no offline copy at all because
    // one PDF was renamed. Take them one at a time and keep what we can get.
    return Promise.all(ASSETS.map(function (u) {
      return c.add(new Request(u, { cache: 'reload' })).catch(function () {});
    }));
  }));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (ks) {
      return Promise.all(ks.map(function (k) {
        if (k.indexOf('woh26-') === 0 && k !== CACHE) return caches.delete(k);
      }));
    }).then(function () {
      return self.clients.claim();
    }).then(function () {
      return self.clients.matchAll({ type: 'window' });
    }).then(function (cs) {
      cs.forEach(function (c) { c.postMessage({ type: 'offline-ready', ver: VER }); });
    })
  );
});

self.addEventListener('fetch', function (e) {
  var r = e.request;
  if (r.method !== 'GET') return;

  var url;
  try { url = new URL(r.url); } catch (err) { return; }
  // Leave anything off-site alone — the Mixcloud link, the analytics beacon.
  if (url.origin !== self.location.origin) return;

  e.respondWith(caches.open(CACHE).then(function (c) {
    return c.match(r, { ignoreSearch: true }).then(function (hit) {
      var net = fetch(r).then(function (res) {
        if (res && res.ok && res.type === 'basic') c.put(r, res.clone());
        return res;
      }).catch(function () {
        // Offline and nothing matched.
        if (hit) return hit;
        // A dated PDF filename this cache does not know about - the page was
        // served from an older cache and is linking to a previous release's
        // filename. Strip the date and use the stable copy, which is always
        // precached, so a printout is never unavailable offline.
        var undated = url.pathname.replace(
          /(we-out-here-2026-(?:set-times|wider-programme))-\d{4}-\d{2}-\d{2}\.pdf$/,
          '$1.pdf');
        if (undated !== url.pathname) {
          return c.match(undated, { ignoreSearch: true }).then(function (alt) {
            if (alt) return alt;
            if (r.mode === 'navigate') return c.match('./index.html');
            return Response.error();
          });
        }
        // A navigation still gets the app shell rather than the browser's
        // dinosaur.
        if (r.mode === 'navigate') return c.match('./index.html');
        return Response.error();
      });
      return hit || net;
    });
  }));
});
