/**
 * Tactical Border Sector Map.
 * Renders an interactive tactical map with BOPs, camera towers, coverage cones,
 * and live blinking breach pings.
 */

window.IBVAP_SectorMap = {
  canvas: null,
  ctx: null,
  breachedCameras: new Set(),
  cameras: [
    { id: "CAM-01-IBB-PETRAPOLE", name: "Tower 7A Zero Line", bop: "BOP Petrapole", x: 0.22, y: 0.52, angle: 90, range: 45 },
    { id: "CAM-02-IBB-ICHAMATI", name: "Ichamati River Reach", bop: "BOP Hasnabad", x: 0.45, y: 0.38, angle: 85, range: 50 },
    { id: "CAM-03-IBB-ICP-ANPR", name: "Petrapole Cargo Gate", bop: "ICP Terminal", x: 0.68, y: 0.62, angle: 180, range: 40 },
    { id: "CAM-04-IBB-DAWKI", name: "Dawki River Outpost", bop: "BOP Dawki 12", x: 0.85, y: 0.48, angle: 175, range: 45 }
  ],

  init() {
    const container = document.getElementById("tactical-sector-map");
    if (!container) return;

    this.canvas = document.createElement("canvas");
    this.canvas.width = container.clientWidth || 800;
    this.canvas.height = container.clientHeight || 180;
    container.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d");

    this.bindClicks();
    this.render();

    // Resize observer
    window.addEventListener("resize", () => {
      if (container.clientWidth > 0 && container.clientHeight > 0) {
        this.canvas.width = container.clientWidth;
        this.canvas.height = container.clientHeight;
        this.render();
      }
    });

    // Animate radar sweep / breach pulses
    setInterval(() => this.render(), 100);
  },

  bindClicks() {
    this.canvas.addEventListener("click", (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;

      const cw = this.canvas.width;
      const ch = this.canvas.height;

      for (const cam of this.cameras) {
        const cx = cam.x * cw;
        const cy = cam.y * ch;
        const dist = Math.hypot(clickX - cx, clickY - cy);
        if (dist < 20) {
          // Switch camera!
          const select = document.getElementById("cam-select");
          if (select) {
            select.value = cam.id;
            select.dispatchEvent(new Event("change"));
          }
          break;
        }
      }
    });
  },

  triggerCameraBreach(cameraId) {
    this.breachedCameras.add(cameraId);
    // Auto-clear breach pulse after 15s if acknowledged
    setTimeout(() => {
      this.breachedCameras.delete(cameraId);
    }, 15000);
  },

  render() {
    if (!this.ctx || !this.canvas) return;

    const cw = this.canvas.width;
    const ch = this.canvas.height;

    // 1. Clear background
    this.ctx.fillStyle = "#070b12";
    this.ctx.fillRect(0, 0, cw, ch);

    // 2. Tactical Grid Lines
    this.ctx.strokeStyle = "rgba(30, 44, 68, 0.4)";
    this.ctx.lineWidth = 1;
    for (let x = 0; x < cw; x += 40) {
      this.ctx.beginPath(); this.ctx.moveTo(x, 0); this.ctx.lineTo(x, ch); this.ctx.stroke();
    }
    for (let y = 0; y < ch; y += 40) {
      this.ctx.beginPath(); this.ctx.moveTo(0, y); this.ctx.lineTo(cw, y); this.ctx.stroke();
    }

    // 3. Draw Zero Line (International Border / Fencing)
    this.ctx.beginPath();
    this.ctx.moveTo(0, ch * 0.45);
    this.ctx.bezierCurveTo(cw * 0.3, ch * 0.35, cw * 0.6, ch * 0.55, cw, ch * 0.40);
    this.ctx.strokeStyle = "#ff5500";
    this.ctx.lineWidth = 3;
    this.ctx.setLineDash([8, 4]);
    this.ctx.stroke();
    this.ctx.setLineDash([]);

    this.ctx.fillStyle = "#ff5500";
    this.ctx.font = "bold 9px 'JetBrains Mono', monospace";
    this.ctx.fillText("--- ZERO LINE (INDO-BANGLADESH BORDER FENCE // SOUTH BENGAL & MEGHALAYA) ---", cw * 0.25, ch * 0.48);

    // 4. Draw Ichamati River Riverine Gap
    this.ctx.fillStyle = "rgba(0, 150, 255, 0.12)";
    this.ctx.beginPath();
    this.ctx.moveTo(cw * 0.40, 0);
    this.ctx.quadraticCurveTo(cw * 0.48, ch * 0.5, cw * 0.42, ch);
    this.ctx.lineTo(cw * 0.50, ch);
    this.ctx.quadraticCurveTo(cw * 0.56, ch * 0.5, cw * 0.48, 0);
    this.ctx.closePath();
    this.ctx.fill();

    // 5. Draw Cameras & Coverage Cones
    const now = Date.now() / 1000;
    for (const cam of this.cameras) {
      const cx = cam.x * cw;
      const cy = cam.y * ch;
      const isBreached = this.breachedCameras.has(cam.id);
      const isSelected = window.IBVAP.activeCameraId === cam.id;

      // Draw FOV Coverage Arc
      const angleRad = (cam.angle * Math.PI) / 180;
      const fovRad = (55 * Math.PI) / 180;
      this.ctx.beginPath();
      this.ctx.moveTo(cx, cy);
      this.ctx.arc(cx, cy, cam.range, angleRad - fovRad / 2, angleRad + fovRad / 2);
      this.ctx.closePath();
      this.ctx.fillStyle = isBreached
        ? "rgba(255, 51, 102, 0.25)"
        : (isSelected ? "rgba(0, 212, 255, 0.2)" : "rgba(0, 229, 163, 0.1)");
      this.ctx.fill();
      this.ctx.strokeStyle = isBreached ? "#ff3366" : (isSelected ? "#00d4ff" : "rgba(0, 229, 163, 0.3)");
      this.ctx.lineWidth = 1;
      this.ctx.stroke();

      // Camera Tower Point
      this.ctx.beginPath();
      this.ctx.arc(cx, cy, 6, 0, Math.PI * 2);
      this.ctx.fillStyle = isBreached ? "#ff3366" : (isSelected ? "#00d4ff" : "#00e5a3");
      this.ctx.fill();
      this.ctx.strokeStyle = "#fff";
      this.ctx.lineWidth = 1.5;
      this.ctx.stroke();

      // Blinking ring if breached
      if (isBreached) {
        const pulse = (Math.sin(now * 8) + 1) / 2;
        this.ctx.beginPath();
        this.ctx.arc(cx, cy, 8 + pulse * 14, 0, Math.PI * 2);
        this.ctx.strokeStyle = `rgba(255, 51, 102, ${1 - pulse})`;
        this.ctx.lineWidth = 2;
        this.ctx.stroke();
      }

      // Tower Label
      this.ctx.fillStyle = isBreached ? "#ff3366" : "#e2e8f0";
      this.ctx.font = "bold 9px 'JetBrains Mono', monospace";
      this.ctx.fillText(`${cam.name} (${cam.bop})`, cx - 35, cy - 10);
    }
  }
};

document.addEventListener("DOMContentLoaded", () => {
  window.IBVAP_SectorMap.init();
});
