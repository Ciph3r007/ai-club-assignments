// Dashboard — fetches the current state of the repo from the GitHub API and
// renders a member × week submission grid. No build step, no data file.
//
// One API call per page load (the git tree endpoint returns every path in the
// repo). GitHub allows ~60 unauthenticated calls/hour/IP, plenty for a club.

(function () {
  // Auto-detect owner/repo when hosted on github.io; fall back to constants.
  const FALLBACK = { owner: "Ciph3r007", repo: "ai-club-assignments", branch: "main" };

  const PLACEHOLDERS = new Set(["dummy.txt", ".gitkeep"]);
  const MEMBER_RE = /^submissions\/(\d+)-([^/]+)$/;
  const SUBMISSION_FILE_RE = /^submissions\/(\d+)-([^/]+)\/week-(\d+)\/(.+)$/;
  const WEEK_PDF_RE = /^tasks\/week-(\d+)\.pdf$/;

  const weekId = n => `week-${String(n).padStart(2, "0")}`;

  function detectRepo() {
    const host = location.hostname;
    if (host.endsWith(".github.io")) {
      const owner = host.split(".")[0];
      const segments = location.pathname.split("/").filter(Boolean);
      const repo = segments[0] || FALLBACK.repo;
      return { owner, repo, branch: FALLBACK.branch };
    }
    return FALLBACK;
  }

  async function fetchTree({ owner, repo, branch }) {
    const url = `https://api.github.com/repos/${owner}/${repo}/git/trees/${branch}?recursive=1`;
    const res = await fetch(url, { headers: { Accept: "application/vnd.github+json" } });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(`GitHub API ${res.status}: ${detail.slice(0, 200)}`);
    }
    const data = await res.json();
    if (data.truncated) {
      console.warn("Tree response was truncated — repo too large for a single call.");
    }
    return data.tree || [];
  }

  function buildModel(tree) {
    const weeksMap = new Map();   // n -> { id, n, taskPdf }
    const membersMap = new Map(); // id -> { id, empId, name, submissions: Set<weekId> }

    for (const entry of tree) {
      const path = entry.path;

      const pdfMatch = path.match(WEEK_PDF_RE);
      if (pdfMatch && entry.type === "blob") {
        const n = parseInt(pdfMatch[1], 10);
        weeksMap.set(n, { id: weekId(n), n, taskPdf: `../${path}` });
        continue;
      }

      const memberMatch = path.match(MEMBER_RE);
      if (memberMatch && entry.type === "tree") {
        const [, empId, name] = memberMatch;
        const id = `${empId}-${name}`;
        if (!membersMap.has(id)) {
          membersMap.set(id, { id, empId, name, submissions: new Set() });
        }
        continue;
      }

      const subMatch = path.match(SUBMISSION_FILE_RE);
      if (subMatch && entry.type === "blob") {
        const [, empId, name, weekN, fileRest] = subMatch;
        const fileName = fileRest.split("/").pop();
        if (PLACEHOLDERS.has(fileName)) continue;
        const id = `${empId}-${name}`;
        if (!membersMap.has(id)) {
          membersMap.set(id, { id, empId, name, submissions: new Set() });
        }
        membersMap.get(id).submissions.add(weekId(parseInt(weekN, 10)));
      }
    }

    const weeks = [...weeksMap.values()].sort((a, b) => a.n - b.n);
    const members = [...membersMap.values()].sort(
      (a, b) => parseInt(a.empId, 10) - parseInt(b.empId, 10)
    );
    return { weeks, members };
  }

  function render({ weeks, members }, repoInfo) {
    // header summary
    const totalCells = members.length * weeks.length;
    let submitted = 0;
    for (const m of members) for (const w of weeks) if (m.submissions.has(w.id)) submitted++;

    document.getElementById("summary").textContent =
      `${members.length} member${members.length === 1 ? "" : "s"} · ` +
      `${weeks.length} week${weeks.length === 1 ? "" : "s"} · ` +
      `${submitted}/${totalCells} submissions`;
    const tsEl = document.getElementById("generatedAt");
    const now = new Date();
    tsEl.dateTime = now.toISOString();
    tsEl.textContent = now.toLocaleString();

    document.getElementById("repoLabel").textContent = `${repoInfo.owner}/${repoInfo.repo}@${repoInfo.branch}`;

    // weeks list
    const weeksList = document.getElementById("weeks-list");
    weeksList.innerHTML = "";
    if (weeks.length === 0) {
      weeksList.innerHTML = '<li class="muted">No weeks published yet.</li>';
    } else {
      for (const w of weeks) {
        const li = document.createElement("li");
        li.innerHTML =
          `<span class="week-id">${w.id}</span>` +
          `<span class="week-title muted">${w.taskPdf.split("/").pop()}</span>` +
          `<a href="${w.taskPdf}" target="_blank" rel="noopener">open PDF →</a>`;
        weeksList.appendChild(li);
      }
    }

    // grid
    document.getElementById("grid-head").innerHTML =
      "<th>Member</th>" + weeks.map(w => `<th>${w.id}</th>`).join("");
    const body = document.getElementById("grid-body");
    body.innerHTML = "";
    if (members.length === 0) {
      body.innerHTML = `<tr><td colspan="${weeks.length + 1}" class="muted">No member folders yet.</td></tr>`;
      return;
    }
    for (const m of members) {
      const tr = document.createElement("tr");
      const cells = weeks
        .map(w => {
          const ok = m.submissions.has(w.id);
          const status = ok ? "submitted" : "pending";
          const symbol = ok ? "✓" : "·";
          return `<td class="cell-wrap"><span class="cell ${status}" title="${status}">${symbol}</span></td>`;
        })
        .join("");
      tr.innerHTML =
        `<td class="member"><span class="empid">${escapeHtml(m.empId)}</span>${escapeHtml(m.name)}</td>` +
        cells;
      body.appendChild(tr);
    }
  }

  function showError(err) {
    document.getElementById("summary").textContent = "Failed to load.";
    const el = document.getElementById("error");
    el.hidden = false;
    el.textContent = String(err.message || err);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function main() {
    const repoInfo = detectRepo();
    try {
      const tree = await fetchTree(repoInfo);
      const model = buildModel(tree);
      render(model, repoInfo);
    } catch (err) {
      showError(err);
      console.error(err);
    }
  }

  main();
})();
