/**
 * Forensic Evidence Capture, Immutable Audit Ledger & Data Minimisation.
 */

window.IBVAP_Forensics = {
  init() {
    this.bindButtons();
    this.loadAuditTrail();
    this.loadWatchlist();
  },

  bindButtons() {
    // 1-Click Evidence Capture Button
    const btnEvidence = document.getElementById("btn-capture-evidence");
    if (btnEvidence) {
      btnEvidence.addEventListener("click", () => {
        window.IBVAP_Player.sendCommand("TRIGGER_EVIDENCE", {
          alert_id: `MANUAL_${Date.now()}`,
          operator_id: window.IBVAP.currentUser?.username || "OPERATOR",
          notes: "Operator 1-click forensic buffer export"
        });
      });
    }

    // Modal Close
    document.getElementById("btn-close-evidence")?.addEventListener("click", () => {
      document.getElementById("modal-evidence").style.display = "none";
    });

    // Verify Hash Chain Button
    document.getElementById("btn-verify-audit")?.addEventListener("click", () => this.verifyAuditChain());

    // 72-Hour Purge Button
    document.getElementById("btn-run-purge")?.addEventListener("click", () => this.run72HourPurge());
  },

  showEvidencePackage(data) {
    const modal = document.getElementById("modal-evidence");
    const container = document.getElementById("evidence-result-content");
    if (!modal || !container) return;

    container.innerHTML = `
      <div style="background:rgba(0,229,163,0.1); border:1px solid #00e5a3; padding:12px; border-radius:4px; margin-bottom:14px;">
        <h4 style="color:#00e5a3; font-size:13px; margin-bottom:6px;">✓ CRYPTOGRAPHIC EVIDENCE PACKAGE SEALED</h4>
        <p style="font-size:11px; color:#e2e8f0;">Captured rolling circular buffer into evidentiary MP4 container with SHA-256 seal.</p>
      </div>

      <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; font-size:11px; background:#070a10; padding:12px; border-radius:4px; border:1px solid #1e2c44;">
        <div><strong>FILE NAME:</strong> <span class="font-mono text-cyan">${data.clip_filename || 'evidence_clip.mp4'}</span></div>
        <div><strong>FRAME COUNT:</strong> <span class="font-mono">${data.frame_count || 150} frames (5.0s buffer)</span></div>
        <div><strong>OPERATOR:</strong> <span>${window.IBVAP.currentUser?.full_name || 'Operator'}</span></div>
        <div><strong>CHAIN OF CUSTODY:</strong> <span class="text-green">ON-PREMISE EDGE SECURE</span></div>
        <div style="grid-column: span 2; margin-top:8px;">
          <strong>SHA-256 DIGITAL INTEGRITY DIGEST:</strong>
          <div class="font-mono text-cyan" style="word-break:break-all; background:rgba(0,0,0,0.5); padding:6px; border-radius:3px; margin-top:4px;">
            ${data.sha256_digest || 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}
          </div>
        </div>
      </div>

      <div style="margin-top:14px; text-align:right;">
        <a href="/data/evidence/${data.clip_filename}" download class="btn-action" style="text-decoration:none; display:inline-block;">DOWNLOAD FORENSIC PACKAGE</a>
      </div>
    `;

    modal.style.display = "flex";
    this.loadAuditTrail();
  },

  async loadAuditTrail() {
    const tbody = document.getElementById("tbody-audit");
    if (!tbody) return;

    try {
      const res = await fetch("/api/audit?limit=50");
      if (!res.ok) return;

      const logs = await res.json();
      document.getElementById("audit-record-count").textContent = logs.length;

      tbody.innerHTML = "";
      logs.forEach(log => {
        const tr = document.createElement("tr");
        const detailsStr = typeof log.details === "object" ? JSON.stringify(log.details) : log.details;

        tr.innerHTML = `
          <td>#${log.id}</td>
          <td>${log.timestamp ? log.timestamp.substring(11, 19) : ''}</td>
          <td>${log.operator_id}</td>
          <td><strong style="color:#00d4ff;">${log.action_type}</strong></td>
          <td style="max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${detailsStr}">${detailsStr}</td>
          <td class="hash-cell">${log.prev_hash ? log.prev_hash.substring(0, 10) + '...' : 'GENESIS'}</td>
          <td class="hash-cell font-mono">${log.sha256_hash ? log.sha256_hash.substring(0, 16) + '...' : ''}</td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      console.warn("Could not load audit trail:", e);
    }
  },

  async verifyAuditChain() {
    const badge = document.getElementById("audit-status-badge");
    try {
      const res = await fetch("/api/audit/verify");
      const data = await res.json();

      if (data.is_valid) {
        if (badge) {
          badge.textContent = `CHAIN INTACT (${data.records_verified} RECORDS VALIDATED)`;
          badge.className = "text-green";
        }
        window.IBVAP?.showToast?.(`Cryptographic Audit Chain Intact! ${data.message} Tamper evidence: 0 alterations.`, "SHA-256 LEDGER VALIDATED");
      } else {
        if (badge) {
          badge.textContent = "TAMPER DETECTED";
          badge.className = "text-red";
        }
        window.IBVAP?.showToast?.(`WARNING: Audit chain verification failed! ${data.message}`, "TAMPER ALERT");
      }
    } catch (e) {
      alert("Verification query error.");
    }
  },

  async loadWatchlist() {
    const faceList = document.getElementById("watchlist-person-list");
    const plateList = document.getElementById("watchlist-plate-list");

    try {
      // 1. Faces
      const resFaces = await fetch("/api/watchlist");
      if (resFaces.ok && faceList) {
        const targets = await resFaces.json();
        faceList.innerHTML = "";
        targets.forEach(t => {
          const card = document.createElement("div");
          card.className = "watchlist-entry-card";
          card.innerHTML = `
            <div class="watchlist-entry-info">
              <h5>${t.name} ${t.alias ? `("${t.alias}")` : ''}</h5>
              <p>ID: ${t.subject_id} • ArcFace: 512-d Normalized Embedding</p>
              <p style="color:#94a3b8; font-size:9px;">${t.notes || ''}</p>
            </div>
            <span class="threat-tag">${t.threat_level}</span>
          `;
          faceList.appendChild(card);
        });
      }

      // 2. Plates
      const resPlates = await fetch("/api/watchlist/plates");
      if (resPlates.ok && plateList) {
        const plates = await resPlates.json();
        plateList.innerHTML = "";
        plates.forEach(p => {
          const card = document.createElement("div");
          card.className = "watchlist-entry-card";
          card.innerHTML = `
            <div class="watchlist-entry-info">
              <h5 class="font-mono text-cyan">${p.plate_number}</h5>
              <p>${p.vehicle_description}</p>
              <p style="color:#94a3b8; font-size:9px;">${p.remarks || ''}</p>
            </div>
            <span class="threat-tag">${p.threat_level}</span>
          `;
          plateList.appendChild(card);
        });
      }
    } catch (e) {
      console.warn("Could not load watchlist:", e);
    }
  },

  async run72HourPurge() {
    const msgEl = document.getElementById("purge-status-msg");
    if (!confirm("Execute 72-Hour Data Minimisation Purge?\n\nThis permanently purges unflagged/un-escalated video chunks and raw frames older than 72 hours while preserving evidentiary audit records.")) {
      return;
    }

    try {
      const res = await fetch("/api/system/purge", {
        method: "POST",
        headers: window.IBVAP.getAuthHeaders()
      });

      if (!res.ok) {
        const err = await res.json();
        alert(`Purge execution failed: ${err.detail || 'Requires Admin privileges'}`);
        return;
      }

      const data = await res.json();
      if (msgEl) {
        msgEl.textContent = `Cleanse Complete: Purged ${data.purged_media_files} expired frame files.`;
        msgEl.className = "text-green";
      }
      this.loadAuditTrail();
    } catch (e) {
      alert("Error contacting purge worker.");
    }
  }
};

document.addEventListener("DOMContentLoaded", () => {
  window.IBVAP_Forensics.init();
});
