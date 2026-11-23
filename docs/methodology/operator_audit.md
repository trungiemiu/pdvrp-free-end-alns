# Open-route destroy/repair audit

## Insertion at the free endpoint

Both single- and multi-objective insertion enumerate pickup position
`len(route)` and delivery position `len(route)+1`. Route evaluation accumulates
only the driver-start-to-first-event and consecutive event arcs. It never adds a
last-event-to-depot arc. Unit tests in `tests/test_independent_route_checker.py`
and `tests/test_open_route_operators.py` lock this behavior.

## Related removal

The retained related operator uses pickup-to-pickup distance,
delivery-to-delivery distance, and a vehicle-type incompatibility penalty. It is
therefore described as spatial related-request removal, not full Shaw removal.
It does not model route position or distance to the free endpoint.

## New tail operators

`tail` destroy searches internal zero-load boundaries and removes the largest
self-contained suffix no larger than the requested destroy size. A zero-load
boundary guarantees that no request picked before the cut is delivered after
the cut. When no internal zero-load suffix is available, it removes requests
with the latest delivery positions and removes both events of each request.

`tail_greedy` repair evaluates only append-pickup-then-delivery placements on
compatible drivers. It cannot introduce a depot return arc and directly exploits
the free route endpoint. With strict vehicle-type compatibility, reassignment is
between compatible drivers, not arbitrarily between different vehicle classes.

The ablation runner contains `no_tail_removal`, `no_tail_repair`, and the joint
`no_tail_operator` configuration. The complete tail-enabled benchmark must be
run in a fresh directory before any performance claim is updated.
