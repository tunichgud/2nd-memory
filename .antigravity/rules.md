# Project Rules for Antigravity Agents

## Stack
- **Backend**: Node.js (Express / Fastify) + Python (FastAPI / scripts)
- **Frontend**: Full-Stack (SSR or SPA)
- **AI Model**: Claude Sonnet (all agents)
- **Language**: English for code & comments; German allowed in planning/docs

---

## Universal Agent Behavior

- Always read existing code before generating new code
- Never delete or overwrite code without explicit confirmation
- Prefer small, focused changes over large rewrites
- Use existing patterns and conventions found in the codebase
- If uncertain about intent → ask before acting, never assume

---

## Code Standards

### Node.js
- Use `async/await` — never raw `.then()` chains
- Prefer functional style: `map`, `filter`, `reduce` over imperative loops
- Use named exports, not default exports (except entry points)
- Error handling: always use `try/catch` with typed errors
- Env vars: always via `process.env`, never hardcoded

### Python
- Use type hints on all function signatures
- Prefer dataclasses or Pydantic models over raw dicts
- Virtual environment assumed: never install globally
- Use `pathlib` over `os.path`

### Both
- No `console.log` / `print` left in production code — use logger
- All functions must have JSDoc / docstring
- Max function length: 40 lines — split if longer

---

## File Naming
- Node.js: `camelCase.js` for modules, `kebab-case.js` for routes
- Python: `snake_case.py`
- Tests: `*.test.js` / `*_test.py` / `test_*.py`
- Docs: `UPPER_CASE.md`

---

## Git Commit Style (Conventional Commits)
```
feat: add user authentication
fix: resolve token expiry bug
docs: update API reference
refactor: extract validation logic
test: add coverage for payment flow
```
