# examdarpan-organic-traffic-agent

An **audit-and-suggest SEO agent** for https://examdarpan.in/. It reads your own public articles, finds SEO problems
and content gaps, optionally adds real Google Search Console data, and writes plain-language reports.

**It is NOT a traffic bot.** It never searches Google for your articles, never clicks results, never fakes visitors,
never edits or publishes content. It cannot promise rankings or traffic. This project is independent from
`examdarpanoffical/examdarpan-seo-ai` and never touches it.

> Status honesty: this code was written and unit-tested offline. It has **not** yet been run against your live site,
> the real Search Console API, a real AI provider, or real GitHub Actions. Treat the first runs as a trial.

## What it does each run (every ~5 minutes)

1. Re-reads the sitemap only every 6 hours (cached), respecting `robots.txt`.
2. Reads **3 articles** per run (new first, then changed, then oldest). Unchanged articles are rechecked weekly.
3. Checks titles, descriptions, headings, thin content, canonicals, noindex, internal links, orphans, duplicates,
   similar titles, old years, passed deadlines, JavaScript-only pages.
4. Builds keyword/topic ideas from each article's own text (no invented volumes).
5. Optional: Search Console (low CTR, few clicks, positions 8-20, declining pages, cannibalization), refreshed once a day.
6. Optional: AI suggestions for 1 article per run.
7. Rewrites reports only if something changed, then commits them.

## Folder structure

```
examdarpan-organic-traffic-agent/
  agent.py                  entry point
  config.yaml               settings (safe to edit)
  requirements.txt  .env.example  .gitignore  README.md
  .github/workflows/agent.yml   the 5-minute schedule
  .github/workflows/tests.yml   runs unit tests when you push
  eda/                      config, logging_utils, http_client, sitemap, extractor, keywords,
                            inventory, seo_analysis, search_console, gsc_analysis, ai_provider, report, runner
  tests/                    unit tests + saved sample XML/HTML
  reports/                  generated reports (START with summary.md)
  data/inventory.json       article inventory (created by the first run)
```

## IMPORTANT: public vs private repository (read this first)

| | Public repo | Private repo |
|---|---|---|
| GitHub Actions minutes | Free, effectively unlimited | ~2,000 free min/month. A 5-minute schedule uses about 8,600 runs/month, so you would run out |
| Who can see your reports | Everyone | Only you |
| Search Console numbers in reports | Keep `reports.show_search_console_numbers: false` (default) | May set it to `true` |

Recommended: **public repo** + default settings. If you want private, change the cron in `.github/workflows/agent.yml`
to `"*/30 * * * *"` or slower, then you can set `show_search_console_numbers: true`.

## Schedule note

You asked for every 4 minutes. GitHub does not support that: the minimum is **5 minutes**, and runs may be delayed or
skipped when GitHub is busy. The workflow uses `*/5 * * * *`. Overlap is prevented with `concurrency`. GitHub can also
pause scheduled workflows in repos with no activity for a long time; if that happens, open the Actions tab and re-enable it.
A free alternative for steadier timing is a small always-on machine (costs money) - not needed to start.

## Setup from an Android phone

**1. Repository name (exact):** `examdarpan-organic-traffic-agent`

**2. Create it:** github.com (Chrome, "Desktop site" helps) > **+** > New repository > name above > Public > do NOT tick
"Add a README" > Create repository.

**3. Unzip the project on your phone** (Files by Google > tap the ZIP > Extract).

**4. Upload files folder by folder.** GitHub's phone upload cannot take folders, but it can upload into any folder if you
open this address (replace YOURNAME): `https://github.com/YOURNAME/examdarpan-organic-traffic-agent/upload/main/FOLDER`
Leave FOLDER empty for the top level. Select all files in that folder on your phone, then tap **Commit changes**.

| Upload into | Files |
|---|---|
| top level (`.../upload/main`) | agent.py, config.yaml, requirements.txt, README.md |
| `eda` | all files from the eda folder |
| `tests` | everything in tests (including `__init__.py`, `helpers.py`) |
| `tests/fixtures` | the 4 sample files |
| `reports` | README.md |

**5. Create the 4 hidden/dot files by hand** (Android file pickers hide them). Use **Add file > Create new file**, type the
file name in the box, paste the contents from the matching file in the `dotfiles-for-phone` folder, and commit:

| File name to type | Copy contents from |
|---|---|
| `.gitignore` | dotfiles-for-phone/gitignore.txt |
| `.env.example` | dotfiles-for-phone/env.example.txt |
| `.github/workflows/agent.yml` | dotfiles-for-phone/agent.yml.txt |
| `.github/workflows/tests.yml` | dotfiles-for-phone/tests.yml.txt |

(Typing `/` in the name box creates folders automatically.)

**6. Enable Actions:** repo > **Actions** tab > if asked, "I understand my workflows, go ahead and enable them".
Then repo > **Settings > Actions > General > Workflow permissions** > choose **Read and write permissions** > Save.

**7. First test:** Actions > **Exam Darpan Organic Traffic Agent** > **Run workflow** > Run. Wait ~1 minute, open the run,
and check that every step has a green tick. Then open `reports/summary.md` in the repo.

**8. Where to look:**
- Reports: the `reports/` folder (`summary.md` first, `issues.csv`, `articles/`).
- Logs: Actions > the run > the "Run the agent" step. On failures or changes, the run also has an **agent-output** artifact.
- Inventory: `data/inventory.json`.

The agent works **without any credentials** (public audit only). Do steps below only if you want more.

## Connect Google Search Console (optional, free)

1. Open console.cloud.google.com > create a project.
2. **APIs & Services > Library** > search "Google Search Console API" > **Enable**.
3. **IAM & Admin > Service Accounts > Create service account** (any name, skip optional roles).
4. Open it > **Keys > Add key > Create new key > JSON**. A file downloads. (If key creation is blocked by an
   organisation policy, you cannot use this method.)
5. Copy the service account's e-mail (ends with `.iam.gserviceaccount.com`).
6. search.google.com/search-console > choose examdarpan.in > **Settings > Users and permissions > Add user** > paste the
   e-mail > permission **Restricted** (read-only).
7. GitHub repo > **Settings > Secrets and variables > Actions > New repository secret**:
   - `GSC_SERVICE_ACCOUNT_JSON` = the **entire contents** of the downloaded JSON file
   - `GSC_SITE_URL` = exactly your property name: `sc-domain:examdarpan.in` (Domain property) or `https://examdarpan.in/` (URL-prefix)
8. Delete the downloaded JSON from your phone. Never put it in the repository.
9. Run the workflow again; `reports/summary.md` should say "Search Console data refreshed".

## Optional AI suggestions

1. Get an API key from your AI provider (Gemini has a free tier, subject to its limits).
2. Add secret `AI_API_KEY`.
3. In `config.yaml` set `ai.provider` to `gemini` (or `openai_compatible` + `base_url`) and check `ai.model` is a current model name.
4. At most 1 article per run is sent (`ai.max_calls_per_run`). AI text is labelled "review before using".

## Secrets summary

| Secret name | Needed for |
|---|---|
| `GSC_SERVICE_ACCOUNT_JSON` | Search Console (optional) |
| `GSC_SITE_URL` | Search Console (optional) |
| `AI_API_KEY` | AI suggestions (optional) |

Secrets are only read from environment variables, never written to files, and are redacted from logs.

## What works without credentials / what needs more

| Feature | Needs |
|---|---|
| Sitemap reading, article inventory, all technical/content checks, keyword ideas, internal-link ideas, reports | Nothing |
| Impressions/clicks/CTR/position, low-CTR and cannibalization findings | Free Google Cloud project + service account |
| AI title/FAQ suggestions | AI key (free tier or paid, your choice) |
| Google Trends | **Not implemented** (no official free API) |
| Automatic publishing | **Not supported** by design |

## Troubleshooting

| Problem | Fix |
|---|---|
| Run is red: "Permission denied ... push" | Settings > Actions > General > Workflow permissions > Read and write |
| "Sitemap discovery failed" | Open https://examdarpan.in/sitemap.xml in a browser; fix `site.sitemap_urls` in config.yaml |
| "blocked by robots.txt" | Your robots.txt disallows the page for this agent; adjust robots.txt if that is unintended |
| Everything flagged `JS_RENDER_SUSPECTED` | Your pages put article text in via JavaScript; the agent only sees raw HTML. Check with URL Inspection in Search Console |
| "access denied (HTTP 403)" for Search Console | Add the service-account e-mail as a user in Search Console; enable the API; check `GSC_SITE_URL` |
| "property not found" | `GSC_SITE_URL` must match exactly (`sc-domain:` vs `https://.../`) |
| No schedule runs happening | Actions tab: re-enable workflows; scheduled runs can be delayed; the workflow file must be on the default branch |
| Too many commits | Normal when articles change. Raise `crawl.recheck_after_days` or `sitemap_refresh_hours` |
| Want to stop everything | Actions > the workflow > ... > Disable workflow |

## Safety design

- `publishing.mode` must be `audit`; any other value is rejected at startup.
- Requests only go to your own site, Google's Search Console API, and the AI provider you choose.
- Polite crawling: robots.txt, 3-second delay, timeouts, retries with backoff, page-size limit, 3 pages/run, 24h cooldown
  after repeated failures.
- A unit test fails if code appears that automates search clicks, browsers, proxies, or similar.

## Running tests (computer or Termux)

```
pip install -r requirements.txt
python -m unittest discover -s tests -t . -v
```

## Honest list of untested items

Not verified against real services: live examdarpan.in HTML structure, real sitemap layout, real Search Console API
responses and quotas, Google service-account authentication, real Gemini/OpenAI responses, GitHub Actions execution
(schedule, cache, push, artifact steps), and GitHub's action versions at the time you use them.
These parts are covered only by simulated (fake) responses in the unit tests.
