/**
 * In-Browser Interactive Tripwire & Polygon Geofence Editor.
 * Allows operators to draw lines and polygon zones directly on the live video canvas
 * and persist them to the edge server.
 */

window.IBVAP_ZoneEditor = {
  isDrawing: false,
  mode: null, // "TRIPWIRE" or "RESTRICTED_POLYGON"
  points: [], // relative coordinates [{x, y}, ...]
  canvas: null,

  init() {
    this.canvas = document.getElementById("live-canvas");
    if (!this.canvas) return;

    this.bindButtons();
    this.bindCanvasEvents();
  },

  bindButtons() {
    const btnTripwire = document.getElementById("btn-draw-tripwire");
    const btnPolygon = document.getElementById("btn-draw-polygon");
    const btnClear = document.getElementById("btn-clear-draw");
    const btnSave = document.getElementById("btn-save-draw");

    if (btnTripwire) {
      btnTripwire.addEventListener("click", () => this.startDrawing("TRIPWIRE"));
    }
    if (btnPolygon) {
      btnPolygon.addEventListener("click", () => this.startDrawing("RESTRICTED_POLYGON"));
    }
    if (btnClear) {
      btnClear.addEventListener("click", () => this.cancelDrawing());
    }
    if (btnSave) {
      btnSave.addEventListener("click", () => this.saveZone());
    }
  },

  bindCanvasEvents() {
    this.canvas.addEventListener("click", (e) => {
      if (!this.isDrawing) return;

      const rect = this.canvas.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width;
      const y = (e.clientY - rect.top) / rect.height;

      this.points.push({ x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)) });

      // If Tripwire, 2 points complete the line
      if (this.mode === "TRIPWIRE" && this.points.length === 2) {
        document.getElementById("btn-save-draw").style.display = "inline-block";
      } else if (this.mode === "RESTRICTED_POLYGON" && this.points.length >= 3) {
        document.getElementById("btn-save-draw").style.display = "inline-block";
      }
    });
  },

  startDrawing(mode) {
    this.isDrawing = true;
    this.mode = mode;
    this.points = [];

    document.getElementById("btn-clear-draw").style.display = "inline-block";
    document.getElementById("btn-save-draw").style.display = "none";

    const tripBtn = document.getElementById("btn-draw-tripwire");
    const polyBtn = document.getElementById("btn-draw-polygon");

    if (mode === "TRIPWIRE") {
      tripBtn.classList.add("active");
      polyBtn.classList.remove("active");
    } else {
      polyBtn.classList.add("active");
      tripBtn.classList.remove("active");
    }
  },

  cancelDrawing() {
    this.isDrawing = false;
    this.mode = null;
    this.points = [];

    document.getElementById("btn-draw-tripwire")?.classList.remove("active");
    document.getElementById("btn-draw-polygon")?.classList.remove("active");
    document.getElementById("btn-clear-draw").style.display = "none";
    document.getElementById("btn-save-draw").style.display = "none";
  },

  async saveZone() {
    if (this.points.length < 2) return;

    const name = prompt(
      "Enter Zone Identifier / Tactical Description:",
      this.mode === "TRIPWIRE" ? "Fencing Inbound Tripwire 3" : "Culvert Buffer Zone"
    );
    if (!name) return;

    const payload = {
      camera_id: window.IBVAP.activeCameraId,
      name: name,
      zone_type: this.mode,
      direction: this.mode === "TRIPWIRE" ? "INBOUND" : "BIDIRECTIONAL",
      coordinates: this.points,
      dwell_threshold_seconds: 90.0,
      severity: "CRITICAL"
    };

    try {
      const res = await fetch("/api/zones", {
        method: "POST",
        headers: window.IBVAP.getAuthHeaders(),
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const err = await res.json();
        alert(`Failed to save zone: ${err.detail || "Access denied"}`);
        return;
      }

      alert("Zone successfully deployed to Edge Detection Engine!");
      this.cancelDrawing();
      window.IBVAP_Forensics?.loadAuditTrail();
    } catch (e) {
      alert("Error saving zone to server.");
    }
  },

  renderPreview(ctx, cw, ch) {
    if (this.points.length === 0) return;

    ctx.save();
    ctx.strokeStyle = "#00e5a3";
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 4]);

    if (this.mode === "TRIPWIRE") {
      ctx.beginPath();
      ctx.moveTo(this.points[0].x * cw, this.points[0].y * ch);
      if (this.points.length > 1) {
        ctx.lineTo(this.points[1].x * cw, this.points[1].y * ch);
      }
      ctx.stroke();
    } else if (this.mode === "RESTRICTED_POLYGON") {
      ctx.beginPath();
      ctx.moveTo(this.points[0].x * cw, this.points[0].y * ch);
      for (let i = 1; i < this.points.length; i++) {
        ctx.lineTo(this.points[i].x * cw, this.points[i].y * ch);
      }
      if (this.points.length >= 3) {
        ctx.closePath();
        ctx.fillStyle = "rgba(0, 229, 163, 0.15)";
        ctx.fill();
      }
      ctx.stroke();
    }

    // Render handle dots at vertices
    for (const p of this.points) {
      ctx.fillStyle = "#00e5a3";
      ctx.beginPath();
      ctx.arc(p.x * cw, p.y * ch, 5, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.restore();
  }
};

document.addEventListener("DOMContentLoaded", () => {
  window.IBVAP_ZoneEditor.init();
});
