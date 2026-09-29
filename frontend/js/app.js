/**
 * IBVAP Master Application Controller.
 * Handles authentication, system clock, navigation tabs, and audio synthesis.
 */

window.IBVAP = {
  authToken: localStorage.getItem("ibvap_token") || null,
  currentUser: JSON.parse(localStorage.getItem("ibvap_user") || "null"),
  activeCameraId: "CAM-01-IBB-PETRAPOLE",
  activeThermalMode: "OPTICAL",
  audioAlarmEnabled: true,
  audioContext: null,

  async init() {
    this.initClock();
    this.initAuth();
    this.initTabs();
    this.initAudio();

    // Ensure session is active, fallback to default BSF operator if no token stored
    await this.ensureAuthenticated();
  },

  showToast(message, title = "TACTICAL NOTICE") {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.style.position = "fixed";
      container.style.top = "70px";
      container.style.right = "20px";
      container.style.zIndex = "99999";
      container.style.display = "flex";
      container.style.flexDirection = "column";
      container.style.gap = "10px";
      container.style.pointerEvents = "none";
      document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.style.background = "rgba(10, 20, 35, 0.95)";
    toast.style.border = "1px solid #00d4ff";
    toast.style.boxShadow = "0 4px 20px rgba(0, 212, 255, 0.3)";
    toast.style.borderRadius = "4px";
    toast.style.padding = "12px 18px";
    toast.style.color = "#ffffff";
    toast.style.fontFamily = "monospace";
    toast.style.fontSize = "13px";
    toast.style.maxWidth = "360px";
    toast.style.pointerEvents = "auto";
    toast.style.transition = "all 0.3s ease";
    toast.innerHTML = `
      <div style="font-weight:bold; color:#00d4ff; margin-bottom:4px; font-size:11px; letter-spacing:1px;">◈ ${title}</div>
      <div style="line-height:1.4;">${message}</div>
    `;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-10px)";
      setTimeout(() => toast.remove(), 350);
    }, 4500);
  },

  initClock() {
    const clockEl = document.getElementById("hdr-clock");
    const update = () => {
      const now = new Date();
      // Format to IST and Zulu
      const istStr = now.toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour12: false });
      const zuluStr = now.toLocaleTimeString("en-GB", { timeZone: "UTC", hour12: false });
      if (clockEl) clockEl.textContent = `${istStr} IST // ${zuluStr} ZULU`;
    };
    update();
    setInterval(update, 1000);
  },

  initAuth() {
    const loginForm = document.getElementById("form-login");
    if (loginForm) {
      loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const u = document.getElementById("login-username").value.trim();
        const p = document.getElementById("login-password").value.trim();
        await this.login(u, p);
      });
    }

    const logoutBtn = document.getElementById("btn-logout");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", () => this.logout());
    }

    document.getElementById("btn-operator-profile")?.addEventListener("click", () => {
      this.showLoginModal();
    });

    document.getElementById("btn-close-login")?.addEventListener("click", () => {
      this.hideLoginModal();
    });

    // Quick role buttons
    document.querySelectorAll(".btn-quick-role").forEach(btn => {
      btn.addEventListener("click", () => {
        document.getElementById("login-username").value = btn.dataset.u;
        document.getElementById("login-password").value = btn.dataset.p;
      });
    });
  },

  async ensureAuthenticated() {
    if (!this.authToken || !this.currentUser) {
      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: "operator", password: "operator123" })
        });
        if (res.ok) {
          const data = await res.json();
          this.authToken = data.access_token;
          this.currentUser = data.user;
          localStorage.setItem("ibvap_token", this.authToken);
          localStorage.setItem("ibvap_user", JSON.stringify(this.currentUser));
          this.updateUserUI();
          window.IBVAP_Alerts?.loadInitialAlerts();
          window.IBVAP_Forensics?.loadAuditTrail();
        }
      } catch (err) {
        console.warn("[IBVAP] Auto-login fallback skipped:", err);
      }
    } else {
      this.updateUserUI();
    }
  },

  async login(username, password) {
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      });
      if (!res.ok) {
        alert("Authentication failed: Invalid credentials");
        return;
      }
      const data = await res.json();
      this.authToken = data.access_token;
      this.currentUser = data.user;
      localStorage.setItem("ibvap_token", this.authToken);
      localStorage.setItem("ibvap_user", JSON.stringify(this.currentUser));

      this.hideLoginModal();
      this.updateUserUI();
      window.IBVAP_Alerts?.loadInitialAlerts();
      window.IBVAP_Forensics?.loadAuditTrail();
      if (this.showToast) {
        this.showToast(`Logged in as ${data.user.full_name} [${data.user.role}]`, "SESSION AUTHORIZED");
      }
    } catch (err) {
      alert("Login server connection error");
    }
  },

  logout() {
    this.authToken = null;
    this.currentUser = null;
    localStorage.removeItem("ibvap_token");
    localStorage.removeItem("ibvap_user");
    this.showLoginModal();
  },

  showLoginModal() {
    const modal = document.getElementById("modal-login");
    if (modal) modal.style.display = "flex";
  },

  hideLoginModal() {
    const modal = document.getElementById("modal-login");
    if (modal) modal.style.display = "none";
  },

  updateUserUI() {
    if (!this.currentUser) return;
    const roleEl = document.getElementById("hdr-operator-role");
    const nameEl = document.getElementById("hdr-operator-name");
    if (roleEl) roleEl.textContent = this.currentUser.role;
    if (nameEl) nameEl.textContent = `${this.currentUser.full_name} (${this.currentUser.badge_number})`;
  },

  initTabs() {
    const tabBtns = document.querySelectorAll(".dock-tab-btn, .tab-btn");
    tabBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        tabBtns.forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-pane-content, .tab-pane").forEach(p => p.classList.remove("active"));

        btn.classList.add("active");
        const targetPane = document.getElementById(btn.dataset.tab);
        if (targetPane) targetPane.classList.add("active");

        // Trigger resize / refresh for map
        if (btn.dataset.tab === "tab-map" && window.IBVAP_SectorMap) {
          window.IBVAP_SectorMap.render();
        } else if (btn.dataset.tab === "tab-audit" && window.IBVAP_Forensics) {
          window.IBVAP_Forensics.loadAuditTrail();
        } else if (btn.dataset.tab === "tab-watchlist" && window.IBVAP_Forensics) {
          window.IBVAP_Forensics.loadWatchlist();
        } else if (btn.dataset.tab === "tab-recurrent" && window.IBVAP_Patrol) {
          window.IBVAP_Patrol.loadRecurrentEncounters();
        } else if (btn.dataset.tab === "tab-mobilization" && window.IBVAP_Patrol) {
          window.IBVAP_Patrol.loadMobilizationOrders();
        }
      });
    });

    // Left Core Navigation Links
    document.querySelectorAll(".nav-link-btn").forEach(link => {
      link.addEventListener("click", () => {
        document.querySelectorAll(".nav-link-btn").forEach(l => l.classList.remove("active"));
        link.classList.add("active");
        const coreTab = link.dataset.coreTab;
        if (coreTab === "tab-map") {
          const mapTabBtn = document.querySelector('.dock-tab-btn[data-tab="tab-map"]');
          mapTabBtn?.click();
        } else if (coreTab === "tab-matrix") {
          window.IBVAP_Player?.setMatrixViewMode(true);
        } else if (coreTab === "tab-uav") {
          window.IBVAP.showToast("UAV Recon feed streaming via Downlink Relay #4.", "AIR RECON UAV ACTIVE");
        }
      });
    });
  },

  initAudio() {
    const soundToggle = document.getElementById("btn-toggle-sound");
    const soundIcon = document.getElementById("sound-icon");
    if (soundToggle) {
      soundToggle.addEventListener("click", () => {
        this.audioAlarmEnabled = !this.audioAlarmEnabled;
        if (soundIcon) {
          soundIcon.textContent = this.audioAlarmEnabled ? "🔊" : "🔇";
        }
      });
    }
  },

  playAlarmSound(severity = "CRITICAL") {
    if (!this.audioAlarmEnabled) return;
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!this.audioContext) {
        this.audioContext = new AudioContext();
      }
      if (this.audioContext.state === "suspended") {
        this.audioContext.resume();
      }

      const osc = this.audioContext.createOscillator();
      const gain = this.audioContext.createGain();
      osc.connect(gain);
      gain.connect(this.audioContext.destination);

      if (severity === "CRITICAL") {
        // High-pitched dual pulse
        osc.frequency.setValueAtTime(880, this.audioContext.currentTime);
        osc.frequency.exponentialRampToValueAtTime(440, this.audioContext.currentTime + 0.25);
        gain.gain.setValueAtTime(0.3, this.audioContext.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, this.audioContext.currentTime + 0.25);
        osc.start();
        osc.stop(this.audioContext.currentTime + 0.25);
      } else {
        // Amber warning ping
        osc.frequency.setValueAtTime(520, this.audioContext.currentTime);
        gain.gain.setValueAtTime(0.2, this.audioContext.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, this.audioContext.currentTime + 0.35);
        osc.start();
        osc.stop(this.audioContext.currentTime + 0.35);
      }
    } catch (e) {
      // Audio autoplay policy fallback
    }
  },

  getAuthHeaders() {
    const token = this.authToken || localStorage.getItem("ibvap_token");
    const headers = { "Content-Type": "application/json" };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  }
};

document.addEventListener("DOMContentLoaded", () => {
  window.IBVAP.init();
});
