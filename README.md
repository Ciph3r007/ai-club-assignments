# DSi AI Club — Weekly Assignments

Shared workspace for the club's weekly individual assignments. Each week the
organisers drop a task PDF; every member submits their solution as a Jupyter
notebook in their own folder, via a Pull Request.

## Layout

```
ai-club-assignments/
├── tasks/                       # weekly task briefs (week-01.pdf, week-02.pdf, …)
├── submissions/
│   └── <empId>-<name>/          # one folder per member, e.g. 539-apu/
│       ├── week-01/             # one folder per week
│       │   └── week-01.ipynb
│       └── library/             # reusable .py modules promoted from past weeks
└── dashboard/                   # static page tracking who submitted what
```

Week numbers are zero-padded to two digits (`week-01`, `week-02`, …) so they
sort lexicographically.

## Workflow for members

1. **Create your folder once:** `submissions/<empId>-<name>/` (lowercase name,
   e.g. `539-apu`). Inside it, also create an empty `library/` for later use.
   Land this via a one-time PR like any other change.
2. **Each week:** read `tasks/week-NN.pdf`, then add your work under
   `submissions/<empId>-<name>/week-NN/` as a single self-contained `.ipynb`
   (no per-week README — the notebook is the doc).
3. **Library graduation (later weeks only):** when a future week's notebook
   wants to reuse helpers from a past one, move that logic into a `.py` inside
   your `library/` and import it from the new notebook. Don't pre-emptively
   split things out — wait until reuse actually happens.
4. **Submit via PR — no direct pushes to `main`.**
   - Branch off `main`. Suggested name: `<empId>-<name>/week-NN`
     (e.g. `539-apu/week-01`).
   - Commit your work, push the branch, open a PR into `main` before the
     weekly deadline.
   - Only modify files inside your own member folder. Don't touch anyone
     else's submissions.

Keep secrets out of notebooks. Use a local `.env`; it's already gitignored.

## Tracking progress — the dashboard

The dashboard is a static page that fetches the current state of `main` from
the GitHub API at load time. There's nothing to regenerate.

- **On GitHub Pages:** once Pages is enabled, it lives at
  `https://ciph3r007.github.io/ai-club-assignments/dashboard/`.
- **Or open it locally:** double-click `dashboard/index.html`. It still pulls
  live state from GitHub (you just need internet); local-only commits won't
  appear until pushed.

A submission cell turns green once the member's `week-NN/` folder on `main`
contains anything other than the placeholder `dummy.txt`.

### Enabling GitHub Pages (one-time, organiser)

1. Push this repo to `main`.
2. Repo settings → Pages → Source: "Deploy from a branch" → Branch: `main`,
   folder: `/ (root)` → Save.
3. After ~1 min the dashboard is live at the URL above.

## Adding a new week (organisers)

Drop the task brief at `tasks/week-NN.pdf` (zero-padded). Open whatever tool
you prefer — Word, Google Docs, Canva, Pages — and export to PDF. The
dashboard picks it up automatically on the next reload; no other wiring
required.

## Naming rules (the dashboard relies on these)

- Member folders: `<empId>-<name>` — digits, dash, lowercase name.
- Week folders inside a member: `week-01`, `week-02`, … — always two digits.
- Task PDFs: `tasks/week-NN.pdf` — same padding.
