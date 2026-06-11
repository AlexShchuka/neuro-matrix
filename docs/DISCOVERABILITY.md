# Discoverability checklist — finish by hand

This repo now ships every discoverability **enabler** that lives in files (marketplace manifest, SEO/GEO README, `llms.txt`, landing page, license). The steps below are the ones that are **GitHub settings or external submissions** — they can't be done in a pull request and need the maintainer's hands. Copy-paste values are inline.

Legend: ☐ todo · ⭐ critical path (without these there is no visibility).

> **Canonical maintainer-action list:** `ROADMAP.md` § "Discoverability — maintainer actions" is the authoritative checklist. This file keeps the press-kit / copy-paste blurbs; update both if adding new action items.

---

## 1. Critical path

### ☐ ⭐ Set the repo About + topics
Repo home → the ⚙️ next to **About** (top-right).
- **Description** (paste):
  ```
  Anti-neuroslop harness for Claude Code: runtime invariants, hooks, four agents, a dual approval+verification gate, and a held-out eval harness that keep AI-assisted coding anchored to reality.
  ```
- **Website**: `https://alexshchuka.github.io/neuro-matrix/`  *(leave blank until Pages is on — see below)*
- **Topics** (add each):
  `claude-code` `claude-code-plugin` `claude-code-marketplace` `ai-agents` `llm` `agentic-ai` `prompt-engineering` `hooks` `subagents` `ai-code-review` `anti-hallucination` `llm-evaluation` `developer-tools` `ai-safety` `constitutional-ai` `systems-thinking`

### ☐ ⭐ Enable GitHub Pages (after the merge to `main`)
Settings → **Pages** → Source: **Deploy from a branch** → Branch: `main` → Folder: `/docs` → Save.
- Wait ~1 min, confirm `https://alexshchuka.github.io/neuro-matrix/` renders.
- Then update `homepage` in `.claude-plugin/marketplace.json` from the repo URL to the Pages URL (small follow-up commit/PR).

---

## 2. Boost channels (backlinks + reach — do after the merge)

Submitting before merge = broken `/plugin marketplace add` for the first visitor. Merge first.

### ☐ Submit to the Anthropic official directory
The curated `anthropics/claude-plugins-official` directory is the primary "Discover" surface; submission goes through their plugin-directory form (expect a quality/security review). **License note:** the project is now under the MIT License (OSI-approved, permissive). Coordinate with issue #4 on what is exposed before submitting. Submission blurb:
```
neuro-matrix is a Claude Code plugin that keeps AI-assisted coding anchored to reality — runtime invariants with a per-turn self-check, four agents (developer/analyzer/critic/epistemic-auditor), hooks, a dual approval+verification gate, and a held-out evaluation harness. Anti-"neuroslop" AI + developer co-system, designed under game theory and systems theory.
```

### ☐ Open PRs into awesome-lists
Highest-ROI discovery channel for Claude Code plugins. For each, read its `CONTRIBUTING`, find the right section (Plugins / Workflow), and add the entry below. Verify the current entry format of each list before submitting (formats change). Note: the project is now under the MIT License (OSI-approved, permissive) — no license-policy blocker for OSI-requiring lists.
- `hesreallyhim/awesome-claude-code` (canonical)
- `ComposioHQ/awesome-claude-plugins`
- `Chat2AnyLLM/awesome-claude-plugins`

Entry (universal `- [name](url) — desc` format):
```markdown
- [neuro-matrix](https://github.com/AlexShchuka/neuro-matrix) — Anti-neuroslop AI + developer co-system: runtime invariants, agents (developer/analyzer/critic/epistemic-auditor), hooks, and a dual approval+verification gate. Keeps AI-assisted coding anchored to reality.
```

### ☐ Publish the Habr article (issue #3) + cross-post
Content is the strongest ranking/citation signal for a new repo. Decide audience (practitioners vs research) and how much to reveal vs hold back (issue #4), then publish and cross-post (dev.to, r/ClaudeAI, X) linking back to the repo.

---

## 3. Press kit (reusable copy for any channel)

**Tagline:** neuro-matrix — anti-neuroslop harness for Claude Code: runtime invariants, review agents, and a dual approval+verification gate that keep AI-assisted coding anchored to reality.

**Install:**
```text
/plugin marketplace add AlexShchuka/neuro-matrix
/plugin install neuro-matrix@neuro-matrix
```

**Show HN / r/ClaudeAI titles:**
- `Show HN: neuro-matrix – a Claude Code plugin that fights "neuroslop" with runtime invariants and a verify-before-commit gate`
- `I built an anti-hallucination harness for Claude Code (invariants + dual approval/verification gate + eval)`

---

## What was already done in files (no action needed)
`.claude-plugin/marketplace.json` · `README.md` hero + Install · `llms.txt` · `docs/index.html` landing · `LICENSE` (MIT) · `COPYRIGHT-NOTICE.md` · `ROADMAP.md` (S2 + this checklist's source).
