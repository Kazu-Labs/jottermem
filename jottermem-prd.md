# PRD: jottermem — a personal, portable memory layer for your AI assistants

**Status:** Draft v1
**Owner:** Allen / Kazu Labs
**Relationship to existing backlog:** Builds on top of the planned **jottermem** local-first embeddable memory library. This PRD scopes jottermem's v1 core plus a consumer-facing layer on top of it, rather than treating them as separate products.

---

## 1. Problem

People increasingly use more than one AI assistant — ChatGPT for one thing, Claude for another, maybe Gemini or a coding agent too. Each one builds its own memory of you, and none of them talk to each other. You end up re-explaining your job, your projects, your preferences, and your ongoing context every time you switch tools. The memory you build up is also not really yours — it lives on the vendor's servers, in their format, accessible only through their product.

The underlying need: **one place, that you own, where your context lives — and any AI you use can read from and write to it.**

## 2. Target user

Primary: **everyday power users of multiple AI assistants** — not developers building agents, but people who use ChatGPT and Claude (and maybe others) regularly enough that re-explaining context is a recurring annoyance. Think: a consultant juggling several clients across tools, a founder using ChatGPT for brainstorming and Claude for writing, a student using different tools for different subjects.

Secondary (enabled, not primary): developers who want to embed the same engine (jottermem-core) into their own agents — this is the existing backlog framing and stays intact as a downstream audience, but the product decisions in this PRD are optimized for the consumer, not the developer.

## 3. Goals

- Give a non-technical user a memory store they can set up in a few minutes, without touching a config file or terminal.
- Store that memory somewhere the user visibly owns: a local folder or their own Google Drive — not a database on our servers.
- Make the same memory usable from at least Claude and ChatGPT, ideally more over time.
- Keep the memory human-readable and editable (plain files), so the user can inspect or fix what's stored without going through us.

## 4. Non-goals (v1)

- Not building a general agent framework — this is a memory layer, not an agent runtime.
- Not trying to auto-capture everything (browsing history, screen activity, etc.) like some competitors do — v1 is explicit, conversational memory, not ambient surveillance-style capture.
- Not supporting every AI tool on day one — start with Claude + ChatGPT, expand later.
- Not building team/shared memory in v1 — single-user only.

## 5. Competitive landscape

This space got crowded fast in 2026. Worth being clear-eyed about it before committing:

- **Native vendor memory** (Claude Memory, ChatGPT Dreaming, Gemini Personal Intelligence, Copilot Memory) — all good within their own product, all explicitly single-platform by design. This is the thing every competitor (including us) is positioning against.
- **Cross-platform memory SaaS**: MemoryRouter, Echo, Supermemory, AI Context Flow, Mem0, MemSync — several of these already do "one memory across ChatGPT/Claude/Gemini" via MCP, mostly as a $15-20/mo hosted subscription where your memory lives on *their* servers.
- **Browser-extension / pull-edit-push tools**: Memory Sync (Chrome extension built around a portable `Memory.md`) is close in spirit to the flat-file approach we discussed.

**Where jottermem can differentiate:** almost everyone above still hosts your memory on their infrastructure — "portable" but not actually "owned." A local-disk-or-your-own-Drive backend, open file format, and an open-source core is a genuinely different claim: *your context never leaves your storage.* That's a real wedge, but it needs validating — "I want to own my data" is a common stated preference that doesn't always translate into people picking the more-annoying-to-set-up option over a smoother $20/mo SaaS. Flagging this as the single biggest open risk in section 10.

## 6. How it works (concept)

1. User picks a backend on setup: a local folder, or a folder in their own Google Drive.
2. jottermem-core manages that folder as a set of flat markdown/JSON files — one file per topic/person/project, similar in spirit to how Claude's own chat memory or Claude Code's `CLAUDE.md` works. A lightweight index file lists what exists so an agent doesn't need to load everything.
3. jottermem exposes that folder to AI assistants as an MCP server: `read_memory`, `write_memory`, `search_memory`, `list_memory` tools.
4. In Claude, this connects directly — Claude Desktop/Code/claude.ai can talk to a local or remote MCP server natively.
5. In ChatGPT, this is where it gets harder (see Architecture, below) — ChatGPT's custom connectors require a *remote* HTTPS MCP endpoint; it cannot talk to a server running only on the user's laptop.
6. The user reviews/edits the files directly at any time — no black box.

## 7. Key user stories

- *"I told ChatGPT about my new job last week. I want Claude to already know that when I open a new chat."*
- *"I want to see and edit exactly what's been remembered about me, in a plain file, not buried in a settings page."*
- *"I switch between my personal Google account and work laptop — I want my memory to follow me, not be stuck on one machine."*
- *"I don't want a company I've never heard of hosting a permanent record of my life on their servers."*

## 8. Architecture

**Backend options:**

| | Local folder | Google Drive |
|---|---|---|
| Setup friction | Low (just pick a folder) | Medium (OAuth to Drive) |
| Works with Claude | Yes — direct via local MCP filesystem server | Yes — via Drive MCP connector |
| Works with ChatGPT | **No, not directly** — ChatGPT's custom connectors require a remote HTTPS endpoint, not a local process | **Yes** — Drive is already remote/HTTPS, so a small cloud-hosted relay that reads/writes the user's Drive via their own OAuth token works fine |
| Cross-device | No (single machine, unless synced separately) | Yes, natively |

**This is the key architectural finding from research this session:** ChatGPT cannot reach a purely local server — it only accepts remote MCP endpoints reached over HTTPS, full stop, as of current OpenAI docs. So "local folder" alone satisfies the Claude side beautifully but **cannot** satisfy the ChatGPT side without either (a) a local tunnel (e.g. Cloudflare/ngrok-style, fragile for a non-technical user) or (b) the Google Drive backend, which is remote by nature and sidesteps the problem entirely.

**Practical implication for scope:** given the target user is a non-technical, multi-assistant user, **Google Drive should probably be the primary/default backend for v1**, with local-folder as a secondary option mainly useful for Claude-only or developer users. This is a scope shift worth deciding on explicitly rather than defaulting to "local first" just because that's the jottermem name/positioning.

**Components:**
1. **jottermem-core** — the file format, read/write/index logic. Local library, open source.
2. **jottermem-relay** — a small hosted service that exposes a user's Drive-backed memory folder as a remote MCP endpoint (OAuth'd to their Drive only, never touches file contents server-side beyond passthrough). This is the one piece that isn't "purely local," and it's the piece that makes ChatGPT support possible at all.
3. **jottermem-app** — the consumer-facing setup experience: pick a backend, connect Claude, connect ChatGPT, browse/edit your memory files.

## 9. Scope

**MVP (small-to-medium tier):**
- Google Drive backend only
- jottermem-relay hosting the MCP endpoint
- Manual connection flow for Claude and ChatGPT (paste server URL / OAuth, following each platform's existing connector flow)
- Flat-file storage: topic-based markdown files + one index file
- Simple desktop/web app to view and hand-edit memory files
- No auto-capture — memory is written either by the user directly, or by an assistant during a conversation when the user asks it to remember something (same pattern as native vendor memory)

**V1 additions:**
- Local-folder backend (Claude-only, for users who don't want Drive)
- Search across memory files (basic keyword, not yet semantic)
- Support for a third platform (Gemini or a coding agent)

**V2+ (not scoped here):**
- Semantic/vector search layer on top of the flat files
- Team/shared memory
- Local network sync between devices without Drive

## 10. Risks & open questions

- **Ownership vs. convenience**: does "your data never leaves your storage" actually win users over competitors offering a smoother one-click SaaS setup? Needs real user validation, not just our own conviction.
- **The Drive-as-default decision** contradicts the "local-first" framing jottermem was originally pitched under — worth deciding deliberately whether jottermem-core stays local-first (for developers embedding it) while the *consumer app* defaults to Drive for practical reasons, or whether that's too confusing a split.
- **ChatGPT connector reliability**: search turned up multiple 2026 reports of ChatGPT's custom MCP connectors being flaky (tools not appearing, OAuth completing but connection failing). Worth a spike before committing real build time, since this directly gates the "works with ChatGPT" claim.
- **Trust/security**: a relay service that touches a user's Drive OAuth token is a real trust ask for a solo/early-stage product — needs a clear, honest story (and probably a security review) before public launch.
- **Crowded market**: several funded/live competitors already do a version of this. Differentiation rests almost entirely on genuine data ownership + open-source core — need to confirm that's defensible and not easily copied.

## 11. Complexity tier & fit with Kazu Labs process

Given the relay service, dual-platform connector work, and app layer, this reads as a **large (>2 weeks)** idea by the existing tiering, likely 2-3 sprints if built as: (1) jottermem-core + Drive backend, (2) relay + Claude connection, (3) ChatGPT connection + app polish. Could be trimmed to medium if MVP drops the polished app and ships as a documented manual setup first, to test the ownership pitch before investing in UX.

**Suggested graduation trigger (draft, needs your sign-off):** a defined number of users successfully connect both Claude and ChatGPT to the same memory folder and report at least one real instance of context carrying over usefully between the two — a signal that the core value prop (not just the setup flow) works, before investing further.

## 12. Success metrics (draft)

- # of users who complete setup (connect at least one assistant)
- # who connect a *second* assistant to the same memory (the actual point of the product)
- Retention: memory files still being read/written after 30 days
- Qualitative: reports of "it remembered something from the other tool" moments

---

## 13. Implementation status (this build)

What's built as of the first pass on this PRD, and how it maps to the scope above:

- **jottermem-core (flat-file format)** — done, as `jottermem.portable`. `PortableStore` reads/writes topic markdown files plus `index.json`, shared with the relay via `jottermem.portable.format` so both backends stay byte-compatible. Kept as a separate module from the existing SQLite/vector `Memory` engine rather than replacing it — that engine remains the embeddable-library product for developers; this is the consumer-facing layer described in this PRD.
- **Local backend + Claude connection** — done. `jottermem-setup` is the wizard from section 8/9: picks local vs. Drive, detects Google Drive for Desktop mount points on macOS, creates the folder, and writes ready-to-paste config for Claude Desktop and Claude Code (`jottermem-portable-mcp`, backed by `JOTTERMEM_PORTABLE_PATH`).
- **jottermem-relay** — scaffolded, deliberately not deployed. `src/jottermem/relay/` has a working FastAPI app (Google OAuth login/callback, a `DriveStore` backend, an MCP endpoint gated by the `mcp` SDK's own token-verifier/resource-server mechanism, a Dockerfile, and a `jottermem-relay-admin` CLI to list/revoke connected accounts) — boot-tested locally with dummy credentials, and `DriveStore`'s read/write/index logic is covered by mock-based tests. As of 2026-08-31, the deliberate call is not to deploy it: doing so means registering a Google Cloud OAuth app and operating a live service under that identity, and the owner isn't ready to take that on for what's currently a personal/exploratory build in a public repo. Nothing about the repo being public forces this — no secret ever gets committed, and the code staying undeployed doesn't block the rest of the product. This means **ChatGPT support is on hold**, since it's the one platform that specifically requires the relay (see section 8's architecture note). The code stays here, tested and ready, for whenever that changes.
- **Search** — basic keyword search only, per the V1 scope line above, not semantic.
- **App / browse-and-edit UI** — done, as `jottermem-app`: a zero-dependency local web view (stdlib `http.server`, bound to `127.0.0.1` only, with a per-run CSRF token on every write so another open tab can't silently inject memory) to see topics/fact counts, add a fact, hand-edit a topic's raw markdown, and delete a topic outright. Local-folder and Drive-for-Desktop-synced folders both work today since it just reads/writes files on disk — this is the actually-supported path for now, and it needs no Google Cloud involvement at all (Drive for Desktop handles the user's Google login itself; jottermem just sees a folder). It doesn't talk to the relay's Drive-API backend directly, which is moot while the relay stays undeployed.
- **Third platform beyond Claude/ChatGPT** — not addressed; any MCP-capable client can use the same local config as Claude Code, so this is more "already possible" than "needs building," but untested against a specific third client.
