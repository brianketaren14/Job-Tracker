/* ── index.js — Job listing & search ─────────────────────── */
"use strict";

const grid = document.getElementById("jobs-grid");
const pagDiv = document.getElementById("pagination");
const resultInfo = document.getElementById("result-info");
const searchInput = document.getElementById("search-input");

let currentPage = 1;
let currentQ = "";
let totalJobs = 0;
const PER_PAGE = 12;

function formatDate(isoStr) {
  if (!isoStr) return null;
  const d = new Date(isoStr);
  if (isNaN(d)) return null;
  return d.toLocaleDateString("id-ID", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function initials(name) {
  if (!name || name === "Not specified") return "?";
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

function buildCard(job) {
  const date = formatDate(job.posted_date_exact);
  const skills = (job.skills || []).slice(0, 5);
  const hasThumb = job.thumbnail && job.thumbnail !== "Not specified";

  const logoHtml = hasThumb
    ? `<div class="card-logo"><img src="${escHtml(job.thumbnail)}" alt="" loading="lazy" onerror="this.parentElement.textContent='${escHtml(initials(job.company_name))}'"></div>`
    : `<div class="card-logo">${escHtml(initials(job.company_name))}</div>`;

  const salaryBadge =
    job.salary && job.salary !== "Not specified"
      ? `<span class="meta-badge salary">
        ${escHtml(job.salary)}
       </span>`
      : "";

  const locBadge =
    job.location && job.location !== "Not specified"
      ? `<span class="meta-badge">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
        ${escHtml(job.location)}
       </span>`
      : "";

  const dateBadge = date
    ? `<span class="meta-badge date">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
        ${escHtml(date)}
       </span>`
    : "";

  const typeBadge =
    job.schedule_type && job.schedule_type !== "Not specified"
      ? `<span class="meta-badge">${escHtml(job.schedule_type)}</span>`
      : "";

  const skillsHtml = skills.length
    ? `<div class="skill-tags">${skills.map((s) => `<span class="skill-tag">${escHtml(s)}</span>`).join("")}${(job.skills || []).length > 5 ? `<span class="skill-tag" style="background:var(--bg-hover);color:var(--text-3)">+${job.skills.length - 5}</span>` : ""}</div>`
    : "";

  const summary =
    job.description_summary && job.description_summary !== "Not specified"
      ? `<p class="card-summary">${escHtml(job.description_summary)}</p>`
      : "";

  return `
    <a href="/job/${job.id_lowongan}" class="job-card">
      <div class="card-top">
        ${logoHtml}
        <div class="card-title-wrap">
          <div class="card-title">${escHtml(job.title || "Untitled")}</div>
          <div class="card-company">${escHtml(job.company_name || "")}</div>
        </div>
      </div>
      <div class="card-meta">${salaryBadge}${locBadge}${typeBadge}${dateBadge}</div>
      ${summary}
      ${skillsHtml}
    </a>`;
}

function escHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildPagination(total, page) {
  const totalPages = Math.ceil(total / PER_PAGE);
  if (totalPages <= 1) {
    pagDiv.innerHTML = "";
    return;
  }

  let html = "";
  const prev = page - 1;
  const next = page + 1;

  html += `<button class="page-btn" ${page === 1 ? "disabled" : ""} onclick="goPage(${prev})">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M15 18l-6-6 6-6"/></svg>
  </button>`;

  const range = [];
  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || (i >= page - 2 && i <= page + 2))
      range.push(i);
    else if (range[range.length - 1] !== "…") range.push("…");
  }
  range.forEach((p) => {
    if (p === "…")
      html += `<span class="page-btn" style="cursor:default">…</span>`;
    else
      html += `<button class="page-btn ${p === page ? "active" : ""}" onclick="goPage(${p})">${p}</button>`;
  });

  html += `<button class="page-btn" ${page === totalPages ? "disabled" : ""} onclick="goPage(${next})">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M9 18l6-6-6-6"/></svg>
  </button>`;

  pagDiv.innerHTML = html;
}

async function loadJobs(page = 1, q = "") {
  currentPage = page;
  currentQ = q;

  // show skeletons
  grid.innerHTML = Array(6)
    .fill(
      `
    <div class="skel-card">
      <div class="skel-row">
        <div class="skeleton skel-circle"></div>
        <div style="flex:1;display:flex;flex-direction:column;gap:.5rem">
          <div class="skeleton skel-line w-80"></div>
          <div class="skeleton skel-line w-40"></div>
        </div>
      </div>
      <div style="display:flex;gap:.5rem">
        <div class="skeleton skel-line" style="width:80px;height:20px;border-radius:99px"></div>
        <div class="skeleton skel-line" style="width:70px;height:20px;border-radius:99px"></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:.35rem">
        <div class="skeleton skel-line w-100"></div>
        <div class="skeleton skel-line w-80"></div>
        <div class="skeleton skel-line w-60"></div>
      </div>
    </div>`,
    )
    .join("");
  pagDiv.innerHTML = "";
  resultInfo.textContent = "";

  try {
    const url = `/api/jobs?page=${page}&per_page=${PER_PAGE}&q=${encodeURIComponent(q)}`;
    const res = await fetch(url);
    const data = await res.json();
    totalJobs = data.total;

    if (!data.jobs || data.jobs.length === 0) {
      grid.innerHTML = `
        <div class="state-empty" style="grid-column:1/-1">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
          </svg>
          <p>Tidak ada lowongan ditemukan${q ? ' untuk "<strong>' + escHtml(q) + '</strong>"' : ""}.</p>
        </div>`;
      return;
    }

    grid.innerHTML = data.jobs.map(buildCard).join("");
    buildPagination(totalJobs, page);

    const start = (page - 1) * PER_PAGE + 1;
    const end = Math.min(page * PER_PAGE, totalJobs);
    resultInfo.textContent = `Menampilkan ${start}–${end} dari ${totalJobs} lowongan${q ? ' · "' + q + '"' : ""}`;
  } catch (err) {
    grid.innerHTML = `<div class="state-empty" style="grid-column:1/-1"><p>Gagal memuat data. Coba lagi.</p></div>`;
  }
}

function goPage(p) {
  window.scrollTo({ top: 0, behavior: "smooth" });
  loadJobs(p, currentQ);
}

// ── Search debounce ───────────────────────────────────────
let debounceTimer;
searchInput.addEventListener("input", () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => loadJobs(1, searchInput.value.trim()), 350);
});
document.getElementById("search-btn").addEventListener("click", () => {
  loadJobs(1, searchInput.value.trim());
});
searchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") loadJobs(1, searchInput.value.trim());
});

// initial load
loadJobs(1, "");
