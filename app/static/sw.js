/* CareCap service worker — presence-only, ZERO caching.

This exists so the app stays installable as a PWA (Chrome requires a
service worker), but it caches nothing: every request goes straight to the
network. This app is a demo/concierge tool that ships continuously, and a
cached app shell has already served stale code to real users twice —
staleness is not a risk this product takes.
*/

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (e) => {
  // Wipe any cache left behind by earlier, caching versions of this worker.
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// No fetch handler on purpose: every request is a normal network request.
