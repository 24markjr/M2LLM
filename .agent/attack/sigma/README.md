# Sigma rules (Phase B5)

Detections in the [Sigma](https://sigmahq.io) format, converted at load time into the same rule model
as `.agent/config/attack_rules.yaml` (`app/cyber/sigma.py`), so a match is cited, mapped and reviewed
exactly like one of those. Written for this project in Sigma form, after the logic of the well-known
community detections they are named for; add more by dropping `.yml` files here.

Supported subset: one or more `selection*` blocks combined by `condition` with `and` / `or` (no
`not`, no `1 of`); field modifiers `contains`, `startswith`, `endswith`, none (exact); a list of
values is any-of. The technique comes from the `attack.tNNNN[.NNN]` tag. A rule outside the subset is
skipped and logged, never half-applied.
