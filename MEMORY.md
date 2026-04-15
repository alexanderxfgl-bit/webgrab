# MEMORY.md - Project Memory

## Architecture
- cascade order: requests > cloudscraper > jina reader API > chrome headless
- each method returns (html_or_none, error_or_none)
- main() tries each in order, stops on first success
- output formats: html, text (strip tags), markdown (basic conversion)

## Decisions
- urllib over requests library (fewer deps, built-in)
- cloudscraper for cloudflare bypass (optional dep)
- jina reader as free fallback API (no key needed for basic use)
- chrome headless as last resort (needs chrome binary on system)
- 200 char minimum response length to filter out error pages
- 50 char minimum for jina (it returns markdown, not html)

## Test Strategy
- unit tests mock all HTTP calls, no network needed
- integration tests use real URLs, marked with pytest markers
- easy URLs: static sites, no JS, no auth
- medium URLs: some JS, cloudflare light, rate limiting
- hard URLs: heavy JS, captchas, auth walls, anti-bot
- xdist for parallel test execution
- coverage enforced at 90% minimum

## Platform Quirks
- Reddit: only old.reddit.com works via plain urllib, cloudscraper gets 403
- Twitter/X: JS wall, needs headless browser
- Cloudflare protected sites: cloudscraper may or may not work depending on challenge type
