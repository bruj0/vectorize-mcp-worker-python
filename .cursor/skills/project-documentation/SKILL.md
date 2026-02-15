---
name: project-documentation
description: Write and maintain project documentation (README, quickstart, production guide) for Cloudflare Python Worker projects. Use when creating, updating, or restructuring documentation files, adding Tables of Contents, or when the user mentions docs, README, quickstart, or production guide.
---

# Project Documentation for Cloudflare Python Workers

Patterns and conventions for the three documentation files in this project. Follow these when creating or updating docs.

## Document Roles

| File | Audience | Purpose |
|------|----------|---------|
| `README.md` | First-time visitors, GitHub browsers | Project overview, feature list, setup summary, API reference, project structure |
| `docs/quickstart.md` | New developers following along step-by-step | Hands-on walkthrough: install, provision, deploy, test every endpoint sequentially |
| `docs/production.md` | Operators deploying and running in production | Infrastructure, config, security, monitoring, scaling, troubleshooting |

### Key principle: no duplication across files

- `README.md` gives the *what* and links to docs/ for the *how*
- `quickstart.md` is a linear tutorial -- every step builds on the previous
- `production.md` is a reference manual -- sections are independent and can be read in any order

## Structure Conventions

### Every doc file must have

1. **Title** -- `# Document Name` as the first line
2. **One-line summary** -- immediately after the title
3. **Table of Contents** -- numbered list linking to all `##` sections
4. **Separator** -- `---` after the TOC (quickstart and production only)

### README.md TOC format

```markdown
## Table of Contents

- [Features](#features)
- [Setup](#setup)
- [API Endpoints](#api-endpoints)
...
```

Unnumbered bullet list (README sections are not sequential steps).

### quickstart.md / production.md TOC format

```markdown
## Table of Contents

1. [Clone and Install](#1-clone-and-install)
2. [Provision Cloudflare Resources](#2-provision-cloudflare-resources)
...
```

Numbered list (sections are sequential or logically ordered).

## Content Patterns

### Deploy-first workflow (no local dev)

Python Workers (Pyodide) have limited local dev support. All documentation assumes a deploy-first workflow:

1. Provision cloud resources (Vectorize, D1, schema, secrets)
2. Deploy with `uv run pywrangler deploy`
3. Test against the live deployed URL with `curl`
4. Debug with `wrangler tail --format=json`

Never reference `uv run pywrangler dev` or `localhost` in documentation. Always use deployed URLs.

### wrangler tail as primary debugging

Every doc should present `wrangler tail` as the primary debugging tool:

```bash
wrangler tail --format=json                   # all logs
wrangler tail --format=json --status error    # errors only
wrangler tail --format=json --method POST     # filter by method
wrangler tail --format=json --search "term"   # filter by content
```

### Shell variables for curl examples

Quickstart sets `$BASE` and `$API_KEY` early, then all curl examples use them:

```bash
BASE="https://worker-name.<subdomain>.workers.dev"
API_KEY="your-key"
```

Production uses literal `https://your-worker-url/` and `YOUR_API_KEY` placeholders (reader picks their own naming).

### Optional features are self-contained

The multimodal worker (image features) is always in its own section, not mixed into other steps:

- **quickstart.md**: Section 8 "Image Features (optional)" -- deploy + test together
- **production.md**: Subsection under "Deployment" -- deploy instructions + comment-out alternative
- **README.md**: Mentioned in setup step 5 with "optional" label

Image endpoint tests are co-located with the multimodal deploy, not in the general test sections.

### Deploy order for service bindings

Always document this constraint:

> The multimodal worker must be deployed **before** the main worker if the `[[services]]` block is present in `wrangler.toml`. After deploying the multimodal worker, **redeploy the main worker**.

### Expected responses

Every curl example in quickstart should show what to expect:

```markdown
Expected: `success: true` with `description` and `extractedText` fields.
```

Or include a full JSON block for critical verification steps (health check, ingest).

## Updating Documentation

When making changes to the codebase that affect docs:

1. **New endpoint** -- add to quickstart (test section), production (operations section), and README (API table)
2. **New binding/resource** -- add to production (infrastructure table + setup steps) and quickstart (provision step)
3. **New config option** -- add to production (configuration section) and update `wrangler.toml.example`
4. **New troubleshooting item** -- add to production (troubleshooting section) and optionally the cloudflare-python-workers skill
5. **Structural change** -- update TOC in all affected files

### Quick Reference table (quickstart only)

Quickstart ends with a table mapping every endpoint to its method, auth requirement, body type, and section link. Update this whenever endpoints change:

```markdown
| Endpoint | Method | Auth | Body | Section |
|----------|--------|------|------|---------|
| `/test`  | GET    | No   | --   | [3](#3-deploy-and-verify) |
```

## Anti-Patterns

- **Don't reference `wrangler dev` or localhost** -- Python Workers need deployed environment
- **Don't duplicate content across files** -- link instead (README links to docs/)
- **Don't mix optional features into required steps** -- keep multimodal in its own section
- **Don't put image tests in the general test section** -- co-locate with multimodal deploy
- **Don't use unnumbered sections in quickstart** -- steps must be numbered for sequential flow
- **Don't forget TOC updates** -- every `##` section must appear in the TOC
