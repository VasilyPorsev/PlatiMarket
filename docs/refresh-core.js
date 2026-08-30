(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.RefreshCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function stamp(product) {
    return String(product.ticks_last_change ?? product.last_change ?? "");
  }

  function partitionProducts(products, cache, now = Date.now(), maxAge = 30 * 60 * 1000) {
    const fresh = [];
    const stale = [];
    for (const product of products) {
      const cached = cache[String(product.product_id)];
      const current = cached
        && String(cached.stamp) === stamp(product)
        && now - Number(cached.checkedAt || 0) < maxAge;
      if (current) fresh.push(cached.result);
      else stale.push(product);
    }
    return { fresh, stale };
  }

  function collectResults(results) {
    return {
      plus: results.flatMap(item => item?.plus ? [item.plus] : []).sort((a, b) => a.price - b.price),
      pro: results.flatMap(item => item?.pro ? [item.pro] : []).sort((a, b) => a.price - b.price),
    };
  }

  function buildNextCache(products, previous, refreshedById, staleIds, checkedAt) {
    const next = {};
    for (const product of products) {
      const id = String(product.product_id);
      const result = refreshedById.has(id)
        ? refreshedById.get(id)
        : staleIds.has(id) ? null : previous[id]?.result;
      if (result) {
        next[id] = {
          stamp: stamp(product),
          checkedAt: refreshedById.has(id) ? checkedAt : previous[id].checkedAt,
          result,
        };
      }
    }
    return next;
  }

  return { stamp, partitionProducts, collectResults, buildNextCache };
});
