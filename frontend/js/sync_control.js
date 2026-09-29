/**
 * Store-and-Forward Edge Synchronization & WAN Offline Simulator.
 */

window.IBVAP_Sync = {
  isOnline: true,

  init() {
    this.bindControls();
    this.pollSyncStatus();
    setInterval(() => this.pollSyncStatus(), 2500);
  },

  bindControls() {
    // Header toggle
    document.getElementById("btn-toggle-link")?.addEventListener("click", () => this.toggleLink());

    // Tab button toggle
    document.getElementById("btn-simulate-link-toggle")?.addEventListener("click", () => this.toggleLink());

    // Force drain button
    document.getElementById("btn-force-sync")?.addEventListener("click", () => this.forceDrain());
  },

  async pollSyncStatus() {
    try {
      const res = await fetch("/api/sync/status");
      if (!res.ok) return;

      const data = await res.json();
      this.isOnline = data.is_link_online;

      // Update Header Indicator
      const hdrStatus = document.getElementById("hdr-link-status");
      if (hdrStatus) {
        if (this.isOnline) {
          hdrStatus.textContent = "ONLINE (HQ SYNC)";
          hdrStatus.className = "value link-status-online";
        } else {
          hdrStatus.textContent = `OFFLINE (${data.pending_backlog_count} QUEUED)`;
          hdrStatus.className = "value link-status-offline";
        }
      }

      // Update Sync Tab Card
      const lamp = document.getElementById("sync-lamp");
      const textStatus = document.getElementById("sync-text-status");
      const btnToggle = document.getElementById("btn-simulate-link-toggle");
      const backlogEl = document.getElementById("sync-backlog-count");
      const alltimeEl = document.getElementById("sync-alltime-count");

      if (lamp) {
        lamp.className = this.isOnline ? "status-lamp" : "status-lamp offline";
      }
      if (textStatus) {
        textStatus.textContent = this.isOnline ? "ONLINE // DIRECT HQ LINK" : "OFFLINE // STORE-AND-FORWARD BUFFERING";
      }
      if (btnToggle) {
        btnToggle.textContent = this.isOnline ? "SIMULATE WAN LINK DROP" : "RESTORE WAN LINK (AUTO-SYNC)";
      }
      if (backlogEl) backlogEl.textContent = `${data.pending_backlog_count} EVENTS`;
      if (alltimeEl) alltimeEl.textContent = `${data.total_synced_all_time} EVENTS`;

    } catch (e) {
      console.warn("Sync status query failed:", e);
    }
  },

  async toggleLink() {
    const targetState = !this.isOnline;
    try {
      const res = await fetch("/api/sync/toggle-link", {
        method: "POST",
        headers: window.IBVAP.getAuthHeaders(),
        body: JSON.stringify({ online: targetState })
      });

      if (!res.ok) {
        const err = await res.json();
        alert(`Failed to toggle link: ${err.detail || 'Unauthorized'}`);
        return;
      }

      this.isOnline = targetState;
      this.pollSyncStatus();
      window.IBVAP_Forensics?.loadAuditTrail();
    } catch (e) {
      alert("Error toggling edge link state.");
    }
  },

  async forceDrain() {
    try {
      const res = await fetch("/api/sync/trigger", { method: "POST" });
      const data = await res.json();
      alert(`Store-and-Forward Sync Complete:\n\nSynced in batch: ${data.synced_in_batch}\nRemaining backlog: ${data.pending_backlog_count}\nStatus: ${data.status}`);
      this.pollSyncStatus();
    } catch (e) {
      alert("Error triggering sync drain.");
    }
  }
};

document.addEventListener("DOMContentLoaded", () => {
  window.IBVAP_Sync.init();
});
