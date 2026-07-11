/* ── detail.js — Job detail page ────────────────────────── */
"use strict";

function escHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatDate(isoStr) {
  if (!isoStr) return null;
  const d = new Date(isoStr);
  if (isNaN(d)) return null;
  return d.toLocaleDateString("id-ID", {
    weekday: "long",
    day: "numeric",
    month: "long",
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

function metaBadge(icon, text, cls = "") {
  if (!text || text === "Not specified") return "";
  return `<span class="meta-badge ${cls}">${icon} ${escHtml(text)}</span>`;
}

async function loadDetail() {
  const skel = document.getElementById("detail-skeleton");
  const content = document.getElementById("detail-content");
  const errDiv = document.getElementById("detail-error");

  try {
    const res = await fetch(`/api/jobs/${JOB_ID}`);
    if (!res.ok) throw new Error("not found");
    const job = await res.json();

    // ── Logo ──
    const logoEl = document.getElementById("d-logo");
    if (job.thumbnail && job.thumbnail !== "Not specified") {
      logoEl.innerHTML = `<img src="${escHtml(job.thumbnail)}" alt="${escHtml(job.company_name)}" onerror="this.parentElement.textContent='${escHtml(initials(job.company_name))}'">`;
    } else {
      logoEl.textContent = initials(job.company_name);
    }

    // ── Title / company ──
    document.getElementById("d-title").textContent = job.title || "Untitled";
    document.getElementById("d-company").textContent = job.company_name || "";
    document.title = `${job.title || "Detail"} · JobRadar`;

    // ── Meta badges ──
    const locIcon = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>`;
    const calIcon = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`;
    const moneyIcon = ``;
    const typeIcon = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>`;

    document.getElementById("d-meta").innerHTML = [
      metaBadge(locIcon, job.location, ""),
      metaBadge(typeIcon, job.schedule_type, ""),
      metaBadge(moneyIcon, job.salary, "salary"),
      metaBadge(calIcon, formatDate(job.posted_date_exact), "date"),
    ].join("");

    // ── Summary ──
    const sumEl = document.getElementById("d-summary");
    sumEl.textContent =
      job.description_summary && job.description_summary !== "Not specified"
        ? job.description_summary
        : "Tidak ada ringkasan tersedia.";

    // ── Description HTML (already sanitized by server) ──
    const descEl = document.getElementById("d-description");
    if (
      job.description &&
      job.description !== "Not specified" &&
      job.description !== "<p>Not specified</p>"
    ) {
      descEl.innerHTML = job.description;
    } else {
      descEl.innerHTML =
        '<p style="color:var(--text-3)">Deskripsi tidak tersedia.</p>';
    }

    // ── Sidebar info ──
    function sideRow(key, val) {
      if (!val || val === "Not specified") return "";
      return `<div class="sidebar-row">
        <span class="sidebar-key">${escHtml(key)}</span>
        <span class="sidebar-val">${escHtml(val)}</span>
      </div>`;
    }
    document.getElementById("d-sidebar").innerHTML = [
      sideRow("Perusahaan", job.company_name),
      sideRow("Lokasi", job.location),
      sideRow("Tipe Kontrak", job.schedule_type),
      sideRow("Gaji", job.salary),
      sideRow("Diposting", formatDate(job.posted_date_exact)),
    ].join("");

    // ── Apply button ──
    const applyBtn = document.getElementById("d-apply-btn");
    if (job.source_link && job.source_link !== "Not specified") {
      applyBtn.href = job.source_link;
    } else {
      applyBtn.style.display = "none";
    }

    // ── Skills ──
    const skillsEl = document.getElementById("d-skills");
    const skills = job.skills || [];
    if (skills.length) {
      skillsEl.innerHTML = skills
        .map((s) => `<span class="skill-tag">${escHtml(s)}</span>`)
        .join("");
    } else {
      skillsEl.innerHTML =
        '<span style="color:var(--text-3);font-size:.82rem">Tidak ada skill tercatat.</span>';
    }

    // ── Show content ──
    skel.style.display = "none";
    content.style.display = "block";
  } catch (e) {
    skel.style.display = "none";
    errDiv.style.display = "block";
  }
}

loadDetail();
