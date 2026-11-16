# OASDelta-TestData

[![Parity report](https://github.com/fluentfoundation/OASDelta-TestData/actions/workflows/parity.yml/badge.svg)](https://github.com/fluentfoundation/OASDelta-TestData/actions/workflows/parity.yml)

Real-world OpenAPI documents, cached as **base/revision pairs** for testing and benchmarking
[OasDelta](https://github.com/fluentfoundation/OASDelta) against [oasdiff](https://github.com/oasdiff/oasdiff). Each
pair is two real versions of one public API, so diffing them exercises what an API actually changes between releases.

## Sources

| Source | Versions | License |
|---|---|---|
| [GitHub REST API](https://github.com/github/rest-api-description) (YAML, ~10 MB) | Commits from Feb, Aug and Nov 2026 | MIT |
| [Stripe API](https://github.com/stripe/openapi), v1 endpoints (`openapi/spec3.json`, JSON, ~8 MB) | Tags v2300, v2500, v2598 | MIT |
| [Stripe API](https://github.com/stripe/openapi/tree/master/latest), v1 and v2 endpoints (`latest/openapi.spec3.json`, the public variant, JSON, ~5 MB) | Tags v2400, v2500, v2596, v2597 (`latest/` changes only with a GA release; v2597 is the latest change) | MIT |
| [Kubernetes](https://github.com/kubernetes/kubernetes/tree/master/api/openapi-spec/v3) every API group and version, `core/v1` to `storagemigration.k8s.io/v1beta1` (JSON, 41 documents) | v1.35.0, v1.36.0, v1.37.0 | Apache-2.0 |
| [Swagger Petstore 3](https://petstore3.swagger.io/) | Weekly snapshots | Apache-2.0 |
| [Sitecore Content API](https://content-api.sitecorecloud.io/swagger/index.html) | Weekly snapshots | None stated |
| [FakeRESTApi](https://fakerestapi.azurewebsites.net/index.html) | Weekly snapshots | None stated |
| [European Patent Office APIs](https://api.apps.epo.org/documentation/swagger-ui/index.html): `v1`, `latest`, `olf20` | Weekly snapshots; `v1` → `latest` is a pair | None stated (EPO terms of use) |

`sources.json` is the definitive list. Only OpenAPI 3.x documents are included, because oasdiff does not read
Swagger 2.0.

## Layout

```
sources.json                         what to fetch: pinned versions (git refs) and live endpoints
specs/<source>/<version>/<file>      each document, byte for byte as served
specs/<source>/<version>/SOURCE.json its URL, retrieval time and sha256
specs/<source>/LICENSE               the upstream license, where there is one
manifest.json                        every source, version and file (generated)
pairs.json                           every base/revision pair, with paths relative to the repo root (generated)
```

## Using the pairs

```sh
python3 tools/check.py --go "$(command -v oasdiff)" --cs "$(command -v oasdelta)"   # parity report over all pairs
jq -r '.pairs[] | "\(.base) \(.revision)"' pairs.json                               # or feed them to anything else
```

A pair can list `skip_commands`, commands that are impractical for it. For example, oasdiff's YAML `diff` of the
Stripe pairs is 5–7 GB.

## Automation

- **[Snapshot live specs](.github/workflows/snapshot.yml)** (weekly) fetches the live endpoints and commits a new
  dated version of any document that changed. The live sources build up version history this way.
- **[Parity report](.github/workflows/parity.yml)** (weekly and on every change) runs the official oasdiff release and
  the latest OasDelta from nuget.org over every pair. It reports differences in the job summary without failing.

## Adding a source

Add an entry to `sources.json`, as `pinned` (git refs at a raw URL template) or `live` (endpoint URLs). Then run
`python3 tools/fetch.py all` and commit `specs/`, `manifest.json` and `pairs.json`. Prefer sources with an open
license and real version history, and record the license.

A pinned source with `"optional_files": true` may lack some of its files in some versions: the Kubernetes API groups
and versions come and go between releases. A file that is not there (HTTP 404) is listed under `missing` in that
version's `SOURCE.json`, and a pair is made only where both versions have the file.

## Licensing

The scripts and configuration in this repository are licensed under Apache-2.0 ([LICENSE](LICENSE)). The documents
under `specs/` belong to their publishers and are redistributed under each source's own license, a copy of which is
in that source's folder. Sources marked "none stated" are publicly served API descriptions, included unmodified, with
attribution, for interoperability testing. If you publish one of them and want it removed, open an issue and it will
be taken down.
