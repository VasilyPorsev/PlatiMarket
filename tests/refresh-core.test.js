const test = require("node:test");
const assert = require("node:assert/strict");
const { partitionProducts, collectResults, buildNextCache } = require("../docs/refresh-core.js");

test("partitionProducts reuses unchanged products and refreshes changed or new ones", () => {
  const products = [
    { product_id: 1, ticks_last_change: 100 },
    { product_id: 2, ticks_last_change: 201 },
    { product_id: 3, ticks_last_change: 300 },
  ];
  const cache = {
    1: { stamp: 100, checkedAt: 9000, result: { plus: { price: 1000 }, pro: null } },
    2: { stamp: 200, checkedAt: 9000, result: { plus: { price: 2000 }, pro: null } },
    9: { stamp: 900, checkedAt: 9000, result: { plus: { price: 9000 }, pro: null } },
  };

  const partition = partitionProducts(products, cache, 10000, 5000);

  assert.deepEqual(partition.fresh, [cache[1].result]);
  assert.deepEqual(partition.stale.map(item => item.product_id), [2, 3]);
});

test("partitionProducts refreshes a cached product after max age", () => {
  const products = [{ product_id: 1, ticks_last_change: 100 }];
  const cache = { 1: { stamp: 100, checkedAt: 1000, result: { plus: null, pro: null } } };

  const partition = partitionProducts(products, cache, 10000, 5000);

  assert.equal(partition.fresh.length, 0);
  assert.deepEqual(partition.stale, products);
});

test("collectResults sorts offers and ignores missing tariffs", () => {
  const results = [
    { plus: { price: 1500, seller: "B" }, pro: null },
    { plus: { price: 900, seller: "A" }, pro: { price: 5000, seller: "A" } },
  ];

  assert.deepEqual(collectResults(results), {
    plus: [{ price: 900, seller: "A" }, { price: 1500, seller: "B" }],
    pro: [{ price: 5000, seller: "A" }],
  });
});

test("buildNextCache does not mark a failed stale refresh as current", () => {
  const products = [
    { product_id: 1, ticks_last_change: 101 },
    { product_id: 2, ticks_last_change: 200 },
  ];
  const previous = {
    1: { stamp: "100", checkedAt: 1, result: { plus: { price: 1000 }, pro: null } },
    2: { stamp: "200", checkedAt: 1, result: { plus: { price: 2000 }, pro: null } },
  };

  const next = buildNextCache(products, previous, new Map(), new Set(["1"]), 5000);

  assert.equal(next["1"], undefined);
  assert.deepEqual(next["2"], { stamp: "200", checkedAt: 1, result: previous[2].result });
});
