# Changelog

Rendered by [git-cliff](https://git-cliff.org) from the conventional commits
behind each tag. `release` rewrites this file in full on every release, so an
edit made here is lost — edit the commit messages instead.

## v2.2.0 — 2026-10-09

### Features

- make the get_roster api public ([#773](https://github.com/Lichess4545/heltour/pull/773)) ([f864f67](https://github.com/Lichess4545/heltour/commit/f864f6770962d2a150c36a8c471363bbb1fa9f70))

### Documentation

- rewrite the README to be shorter and easier to follow ([6b64953](https://github.com/Lichess4545/heltour/commit/6b64953b58c9c15915e56c52a6473e3f12951b82))

### Tooling

- **deploy**: deploy production 2.1.0 ([e55bad1](https://github.com/Lichess4545/heltour/commit/e55bad183b19704d1d252510a54ec5c31ae58ecd))

## v2.1.0 — 2026-10-09

### Features

- use django database celery backends ([a1a95f3](https://github.com/Lichess4545/heltour/commit/a1a95f3cfb75a0e1aefeeaca28e4c873d262d414))
- use the devenv to provide a development environment ([f5673f0](https://github.com/Lichess4545/heltour/commit/f5673f0a55c9dd3f45041b9d501712cc94f9a13d))
- **tournament**: add a seed_test_data command that seeds demo leagues ([#797](https://github.com/Lichess4545/heltour/pull/797)) ([dab1283](https://github.com/Lichess4545/heltour/commit/dab12839d3a411c71f70a6529bc31a63d1ac36e1))
- adding the deployed version to the footer and adding a deploy command ([44a9468](https://github.com/Lichess4545/heltour/commit/44a9468d4514e493c30944b0e3f37ca4722e78bf))

### Fixes

- stop logging successful Lichess messages as send failures ([c597ccc](https://github.com/Lichess4545/heltour/commit/c597ccca32aa4d831a56c14973f2293fbfc207f3))
- result is a json, not a simple string ([#729](https://github.com/Lichess4545/heltour/pull/729)) ([f39376f](https://github.com/Lichess4545/heltour/commit/f39376fd46a6b7ea24adb037cbf73e13c10d77ef))

### Tests

- PlayerProfileView tests ([307ca2d](https://github.com/Lichess4545/heltour/commit/307ca2d70140cb0ee22170d63a2a943209fb1752))
- more tests for notify.py ([#735](https://github.com/Lichess4545/heltour/pull/735)) ([8b62f45](https://github.com/Lichess4545/heltour/commit/8b62f45cb80827e653c4f2637f105717c2f91597))
- more automod tests ([#697](https://github.com/Lichess4545/heltour/pull/697)) ([5f3e209](https://github.com/Lichess4545/heltour/commit/5f3e209b1b0a5ec9ce9a9a9b5f5673e7f3b4c5b9))

### Tooling

- refactor the stack to have per service secrets and remove staging. ([c34d480](https://github.com/Lichess4545/heltour/commit/c34d480ddb91003630e34a1bd9952ee27a30e1f1))
- remove the bare-metal deploy ([#795](https://github.com/Lichess4545/heltour/pull/795)) ([d5a1ba2](https://github.com/Lichess4545/heltour/commit/d5a1ba2ec5a3e6e26769747672c79393b664141f))
- **deps**: bump python dependencies with security fixes ([f082b00](https://github.com/Lichess4545/heltour/commit/f082b007a6f4537d78f4ce86eac607d0ba03a5b7))
- add a slightly reworded version of the lichess/ghostty ai-policy ([c6b8a45](https://github.com/Lichess4545/heltour/commit/c6b8a45360568457107c430c542b509d62483aca))
- use devenv allocated ports properly  ([41d92a1](https://github.com/Lichess4545/heltour/commit/41d92a1d040f64fc867f13614c0af6d3c1e950c2))

### Other

- initial tests for the api ([32851f9](https://github.com/Lichess4545/heltour/commit/32851f974f3cb9656fabbf09c39c2a29aea27938))

## v2.0.4 — 2026-10-08

### Fixes

- **deploy**: issue certificates through Traefik's DNS challenge resolver ([#790](https://github.com/Lichess4545/heltour/pull/790)) ([ac8823b](https://github.com/Lichess4545/heltour/commit/ac8823b52ea3e0e893408c86626f4341bd005f83))

## v2.0.3 — 2026-10-08

### Fixes

- **deploy**: drop the web and caddy placement constraints ([#789](https://github.com/Lichess4545/heltour/pull/789)) ([0f7a6b2](https://github.com/Lichess4545/heltour/commit/0f7a6b222cd5309ed40f8d582946b93841877fee))

## v2.0.2 — 2026-10-08

### Fixes

- **release**: bump the production stack on stable releases ([dd75bb3](https://github.com/Lichess4545/heltour/commit/dd75bb336a543811ec0f9249082b1d2fb16beb5c))

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

