# Changelog

Rendered by [git-cliff](https://git-cliff.org) from the conventional commits
behind each tag. `release` rewrites this file in full on every release, so an
edit made here is lost — edit the commit messages instead.

## v2.0.1 — 2026-10-08

### Fixes

- **deploy**: route caddy through the shared Traefik on the frontend network ([0379edd](https://github.com/Lichess4545/heltour/commit/0379edd77b201110043bd163e0821ccb10d0c4d0))

## v2.0.0 — 2026-10-08

### Features

- new backup/restore scripts ([c152599](https://github.com/Lichess4545/heltour/commit/c15259915fd4639af339114b829fd1f1f667f4b4))
- **breaking** — use environment variables, and re-organize settings for new deployments ([0f876f3](https://github.com/Lichess4545/heltour/commit/0f876f3852d81ef289984c95db699405691401dc))
- build a nix container image and release it to ghcr.io ([47eb4e9](https://github.com/Lichess4545/heltour/commit/47eb4e9072766dcc51a3eab435895108ac452c7c))
- add production and staging swarm stacks deployed through Portainer ([8bd6928](https://github.com/Lichess4545/heltour/commit/8bd692863186b828100c3cc253ec6082702b0e65))

### Fixes

- switching to python3.9 ([1547079](https://github.com/Lichess4545/heltour/commit/1547079ae4c5e538c0d8563384914c4679e8db14))
- updated deps ([f36ff21](https://github.com/Lichess4545/heltour/commit/f36ff216acfd536d1479e6f9b7f8bab6b3fc2879))
- Add this setting ([850f502](https://github.com/Lichess4545/heltour/commit/850f502c1a7cbf39ae9c7ff68b517533b738cb3d))
- Must start with the scheme ([63c599d](https://github.com/Lichess4545/heltour/commit/63c599dc21a57b810decf123723e4844cc61139f))
- Updated poetry.lock ([b8b9004](https://github.com/Lichess4545/heltour/commit/b8b9004ea126c273037f758517eda4475a4b1b66))
- Fix storages setting ([4a486fa](https://github.com/Lichess4545/heltour/commit/4a486fa4956e1ddb6318be1b64672381e242269a))
- Always reset the db on start. ([80ae906](https://github.com/Lichess4545/heltour/commit/80ae9063464445cc8c348cb82856811e9e6b2a03))
- Reset usernames as well (just in case) ([d176521](https://github.com/Lichess4545/heltour/commit/d176521343d9aba755627664c39eea9b69f59727))
- Merging migrations ([51e0a74](https://github.com/Lichess4545/heltour/commit/51e0a7421eb88968b914abbdd43cf03ec049bed0))
- Remove android app ([b668631](https://github.com/Lichess4545/heltour/commit/b668631b8988229108ed5749b0ba592d755f1fa7))
- Fix invite of chesster ([0d0321a](https://github.com/Lichess4545/heltour/commit/0d0321af1f7fb8707e9787d57f039d2546c79d7f))
- Always set pending on creation ([1e850f7](https://github.com/Lichess4545/heltour/commit/1e850f735e8aa57decbea82351161177c54a4123))
- logs ([a6e725b](https://github.com/Lichess4545/heltour/commit/a6e725b7343da9f7f7ede52265c2aabdf4526233))
- Protecsnek ([a2edb79](https://github.com/Lichess4545/heltour/commit/a2edb7942071581b28114c765980ae62d22f5d70))
- protecsnek ([91d1bf3](https://github.com/Lichess4545/heltour/commit/91d1bf35eb95fec93e4c4984689b9868dcc92b9d))
- new rate limits ([3a375a8](https://github.com/Lichess4545/heltour/commit/3a375a8e180a02d9857c2dba0d587cc60dcbe524))
- minor refactor ([d72d7f4](https://github.com/Lichess4545/heltour/commit/d72d7f43bf227b7da2060aa0865ff876478b69d0))
- minor tweak for the latest season query as well ([f6869e1](https://github.com/Lichess4545/heltour/commit/f6869e10cdc0079eb53e51918a9b44a9fb924f5d))
- minor refactor ([853de36](https://github.com/Lichess4545/heltour/commit/853de366dab9b64864d2edf02d44e26d7fff93db))
- minor tweak for the latest season query as well ([a7abd64](https://github.com/Lichess4545/heltour/commit/a7abd646d55ee721c8caedca50f6df83851a2b6f))
- merging migrations ([570b9b2](https://github.com/Lichess4545/heltour/commit/570b9b24dee8d1af753eb3f681b8682dc58c2aa9))
- Hide this for now ([48ff5d2](https://github.com/Lichess4545/heltour/commit/48ff5d2397e24ce33ec7707b9beebb106c058d65))
- indentation ([43f92e5](https://github.com/Lichess4545/heltour/commit/43f92e528b487c69cec6aef6d6404f7a82a93c92))
- Add more-itertools ([bfb05a6](https://github.com/Lichess4545/heltour/commit/bfb05a6326987baf95f2c39232c00eb189e3affd))
- Don't send registration received emails. ([2c65f65](https://github.com/Lichess4545/heltour/commit/2c65f65bc82189c255e0adf9203bd20bd04a0559))
- update start.sh to make it more modern and resilient, straight to master ([7659c4a](https://github.com/Lichess4545/heltour/commit/7659c4a0499071a279972bf0ff00eb73682a3798))
- start the devenv takeover ([ffe0c58](https://github.com/Lichess4545/heltour/commit/ffe0c5858249f02ae1db22355264fea13f3855a4))

### Other

- add calendar link to intro message ([39eca91](https://github.com/Lichess4545/heltour/commit/39eca914e475240a0f00e478e22a03e602c2facd))
- use api for sending mail ([e526b25](https://github.com/Lichess4545/heltour/commit/e526b257ede03f766bb42def33472b0781b5dc27))
- fix small formatting problem ([f39d150](https://github.com/Lichess4545/heltour/commit/f39d15052e5bfa634846f19ed7a1a69110f433da))

