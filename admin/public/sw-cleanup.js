// Service Worker: clear old caches + register new SW
if ("serviceWorker" in navigator) {
  // Unregister all old service workers first
  navigator.serviceWorker.getRegistrations().then(function (regs) {
    regs.forEach(function (r) {
      r.unregister();
    });
  });
  // Clear all caches
  if ("caches" in window) {
    caches.keys().then(function (names) {
      names.forEach(function (n) {
        caches.delete(n);
      });
    });
  }
  window.addEventListener("load", function () {
    navigator.serviceWorker
      .register("./sw.js")
      .then(function (reg) {
        console.log("SW registered:", reg.scope);
      })
      .catch(function (err) {
        console.log("SW registration failed:", err);
      });
  });
}
