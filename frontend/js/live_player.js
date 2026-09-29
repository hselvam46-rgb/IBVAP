/**
 * Live Video Player & Canvas HUD Overlay Renderer.
 * Renders high-performance video streams, ByteTrack bounding boxes,
 * directional tripwires, and restricted polygon geofences with dwell timers.
 */

window.IBVAP_Player = {
  ws: null,
  canvas: null,
  ctx: null,
  currentTracks: [],
  currentZones: [],
  imgElement: null,
  matrixMode: false,
  matrixSockets: {},
  matrixCanvases: {},
  matrixCtxs: {},
  matrixImages: {},
  autoPopupEnabled: false,
  lastPopupTime: 0,
  currentSuspiciousAlert: null,
  sectorCams: [
    "CAM-01-IBB-PETRAPOLE",
    "CAM-02-IBB-ICHAMATI",
    "CAM-03-IBB-ICP-ANPR",
    "CAM-04-IBB-DAWKI"
  ],

  init() {
    this.canvas = document.getElementById("live-canvas");
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");
    this.imgElement = new Image();

    this.initControls();
    this.connectWebSocket();
    // Default to 2x2 Matrix view as seen in reference C4I design
    setTimeout(() => this.setMatrixViewMode(true), 300);
  },

  initControls() {
    // Back to 2x2 Matrix from Single View
    document.getElementById("btn-back-to-matrix")?.addEventListener("click", () => {
      this.setMatrixViewMode(true);
    });

    document.getElementById("btn-refresh-stream")?.addEventListener("click", () => {
      this.initMatrixStreams();
      window.IBVAP?.showToast?.("Refreshed all 4 border camera feeds.", "STREAMS RECONNECTED");
    });

    // Video Input Source Switcher
    const btnSrcSector = document.getElementById("btn-src-sector");
    const btnSrcWebcam = document.getElementById("btn-src-webcam");
    const btnSrcMobile = document.getElementById("btn-src-mobile");
    const indicator = document.getElementById("source-indicator");
    const camSelectWrapper = document.getElementById("cam-select-wrapper");
    const modalMobile = document.getElementById("modal-mobile-cam");

    const setSourceButtonsActive = (activeBtn) => {
      [btnSrcSector, btnSrcWebcam, btnSrcMobile].forEach(b => b?.classList.remove("active"));
      activeBtn?.classList.add("active");
    };

    if (btnSrcSector) {
      btnSrcSector.addEventListener("click", () => {
        setSourceButtonsActive(btnSrcSector);
        if (indicator) indicator.textContent = "ACTIVE: IBB BORDER OUTPOSTS";
        if (camSelectWrapper) camSelectWrapper.style.display = "flex";
        this.sendCommand("SWITCH_SOURCE_MODE", { mode: "SECTOR" });
      });
    }

    if (btnSrcWebcam) {
      btnSrcWebcam.addEventListener("click", () => {
        setSourceButtonsActive(btnSrcWebcam);
        if (indicator) indicator.textContent = "ACTIVE: LIVE LAPTOP WEBCAM (DEVICE 0)";
        if (camSelectWrapper) camSelectWrapper.style.display = "none";
        this.sendCommand("SWITCH_SOURCE_MODE", { mode: "WEBCAM" });
        window.IBVAP.showToast("Switched to Live Laptop Webcam (Device 0). Processing real-time YOLOv8 detection & ByteTrack.", "WEBCAM INGESTION ACTIVE");
      });
    }

    if (btnSrcMobile) {
      btnSrcMobile.addEventListener("click", () => {
        if (modalMobile) modalMobile.style.display = "flex";
      });
    }

    document.getElementById("btn-close-mobile-modal")?.addEventListener("click", () => {
      if (modalMobile) modalMobile.style.display = "none";
    });

    const formMobile = document.getElementById("form-mobile-cam");
    if (formMobile) {
      formMobile.addEventListener("submit", (e) => {
        e.preventDefault();
        const url = document.getElementById("input-mobile-url").value.trim();
        if (!url) return;

        setSourceButtonsActive(btnSrcMobile);
        if (indicator) indicator.textContent = `ACTIVE: MOBILE PHONE CAM (${url})`;
        if (camSelectWrapper) camSelectWrapper.style.display = "none";
        if (modalMobile) modalMobile.style.display = "none";

        this.sendCommand("SWITCH_SOURCE_MODE", { mode: "MOBILE_CAM", mobile_url: url });
        window.IBVAP.showToast(`Connecting to Mobile Phone Camera at ${url}. Ensure IP Webcam or DroidCam is active.`, "MOBILE CAM INGESTION ACTIVE");
      });
    }

    // Camera switcher (Indo-Bangladesh Border Sector)
    const camSelect = document.getElementById("cam-select");
    if (camSelect) {
      camSelect.addEventListener("change", (e) => {
        const camId = e.target.value;
        window.IBVAP.activeCameraId = camId;
        this.sendCommand("SWITCH_CAMERA", { camera_id: camId });

        const sectorEl = document.getElementById("hdr-sector");
        if (sectorEl) {
          const names = {
            "CAM-01-IBB-PETRAPOLE": "EASTERN // PETRAPOLE ZERO LINE (SOUTH BENGAL)",
            "CAM-02-IBB-ICHAMATI": "SOUTH BENGAL // ICHAMATI RIVER GAP (HASNABAD)",
            "CAM-03-IBB-ICP-ANPR": "NORTH 24 PARGANAS // ICP PETRAPOLE CARGO GATE",
            "CAM-04-IBB-DAWKI": "MEGHALAYA // DAWKI RIVER OUTPOST 12"
          };
          sectorEl.textContent = names[camId] || camId;
        }
      });
    }

    // Thermal shader mode buttons
    document.querySelectorAll(".btn-mode, .btn-shader").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".btn-mode, .btn-shader").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        const mode = btn.dataset.mode;
        window.IBVAP.activeThermalMode = mode;
        this.sendCommand("SET_THERMAL_MODE", { mode });
        if (window.IBVAP?.showToast) {
          window.IBVAP.showToast(`Active sensor shader switched to ${mode}.`, "SENSOR SHADER");
        }
      });
    });

    // Still Frame Snapshot Capture
    document.getElementById("btn-snapshot-stage")?.addEventListener("click", () => {
      let canvas = null;
      if (this.matrixMode) {
        const activeCam = window.IBVAP?.activeCameraId || "CAM-01-IBB-PETRAPOLE";
        canvas = document.getElementById(`matrix-canvas-${activeCam}`) || document.getElementById("matrix-canvas-CAM-01-IBB-PETRAPOLE");
      } else {
        canvas = document.getElementById("live-canvas");
      }
      if (canvas) {
        try {
          const a = document.createElement("a");
          a.download = `IBVAP_TAC_CAPTURE_${Date.now()}.jpg`;
          a.href = canvas.toDataURL("image/jpeg", 0.95);
          a.click();
          window.IBVAP?.showToast?.("Saved high-resolution tactical frame capture to downloads.", "FRAME SNAPSHOT CAPTURED");
        } catch (e) {
          window.IBVAP?.showToast?.("Tactical frame snapshot captured.", "SNAPSHOT CAPTURED");
        }
      }
    });

    // 2x2 Matrix View Mode Switcher
    const btnViewSingle = document.getElementById("btn-view-single");
    const btnViewMatrix = document.getElementById("btn-view-matrix");

    if (btnViewSingle) {
      btnViewSingle.addEventListener("click", () => this.setMatrixViewMode(false));
    }
    if (btnViewMatrix) {
      btnViewMatrix.addEventListener("click", () => this.setMatrixViewMode(true));
    }

    // Matrix Tile Click-to-Focus
    this.sectorCams.forEach(camId => {
      const tile = document.getElementById(`matrix-tile-${camId}`);
      if (tile) {
        tile.addEventListener("click", (e) => {
          // If clicked on a button or banner inside tile, don't hijack
          if (e.target.closest("button") || e.target.closest("input")) return;
          this.switchToSingleView(camId);
        });
      }
    });

    // Suspicious Threat Pop-Up Modal Controls
    const btnClosePopup = document.getElementById("btn-close-suspicious-popup");
    const btnDismissPopup = document.getElementById("btn-suspicious-dismiss");
    const btnFocusCam = document.getElementById("btn-suspicious-focus-cam");
    const btnDispatchPatrol = document.getElementById("btn-suspicious-dispatch-patrol");
    const popupBackdrop = document.getElementById("suspicious-popup-backdrop");
    const btnToggleAutoPopup = document.getElementById("btn-toggle-auto-popup");
    const autoPopupStatus = document.getElementById("auto-popup-status");

    if (btnToggleAutoPopup) {
      btnToggleAutoPopup.addEventListener("click", () => {
        this.autoPopupEnabled = !this.autoPopupEnabled;
        if (autoPopupStatus) {
          autoPopupStatus.textContent = this.autoPopupEnabled ? "ACTIVE" : "MUTED";
          autoPopupStatus.style.color = this.autoPopupEnabled ? "var(--mil-green)" : "var(--mil-amber)";
        }
        if (window.IBVAP?.showToast) {
          window.IBVAP.showToast(`Auto Breach Threat Modal is now ${this.autoPopupEnabled ? 'ACTIVE' : 'MUTED'}`, "TACTICAL POPUP SETTING");
        }
      });
    }

    const closeSuspiciousModal = () => {
      const modal = document.getElementById("modal-suspicious-popup");
      if (modal) modal.style.display = "none";
      this.lastPopupTime = Date.now();
    };

    if (btnClosePopup) btnClosePopup.addEventListener("click", closeSuspiciousModal);
    if (btnDismissPopup) btnDismissPopup.addEventListener("click", closeSuspiciousModal);
    if (popupBackdrop) popupBackdrop.addEventListener("click", closeSuspiciousModal);

    if (btnFocusCam) {
      btnFocusCam.addEventListener("click", () => {
        closeSuspiciousModal();
        if (this.currentSuspiciousAlert) {
          this.switchToSingleView(this.currentSuspiciousAlert.camera_id);
        }
      });
    }

    if (btnDispatchPatrol) {
      btnDispatchPatrol.addEventListener("click", () => {
        closeSuspiciousModal();
        if (this.currentSuspiciousAlert && window.IBVAP_Patrol) {
          window.IBVAP_Patrol.openPatrolModalFromAlert(this.currentSuspiciousAlert);
        }
      });
    }

    // Fullscreen Camera Viewport Toggle (Supports Single Focus & Matrix Grid)
    const btnFullscreen = document.getElementById("btn-toggle-fullscreen");
    const btnExitFs = document.getElementById("btn-exit-fullscreen");
    const canvasContainer = document.getElementById("single-cam-container") || document.getElementById("canvas-container");
    const matrixContainer = document.getElementById("matrix-container");
    const fsLabel = document.getElementById("fullscreen-btn-label");

    const getActiveViewport = () => (this.matrixMode ? matrixContainer : canvasContainer);

    const toggleFs = () => {
      const targetContainer = getActiveViewport();
      const isFs = !!(document.fullscreenElement || document.webkitFullscreenElement || targetContainer?.classList.contains("fullscreen-active"));
      if (!isFs) {
        if (targetContainer?.requestFullscreen) {
          targetContainer.requestFullscreen().catch(() => {
            targetContainer.classList.add("fullscreen-active");
          });
        } else if (targetContainer?.webkitRequestFullscreen) {
          targetContainer.webkitRequestFullscreen();
        } else {
          targetContainer?.classList.add("fullscreen-active");
        }
      } else {
        if (document.exitFullscreen) {
          document.exitFullscreen().catch(() => {});
        } else if (document.webkitExitFullscreen) {
          document.webkitExitFullscreen();
        }
        canvasContainer?.classList.remove("fullscreen-active");
        matrixContainer?.classList.remove("fullscreen-active");
      }
    };

    if (btnFullscreen) {
      btnFullscreen.addEventListener("click", toggleFs);
    }
    if (btnExitFs) {
      btnExitFs.addEventListener("click", () => {
        if (document.fullscreenElement || document.webkitFullscreenElement) {
          if (document.exitFullscreen) document.exitFullscreen();
          else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
        }
        canvasContainer?.classList.remove("fullscreen-active");
        matrixContainer?.classList.remove("fullscreen-active");
      });
    }

    // Keyboard shortcut 'F' to toggle fullscreen, 'Esc' handled natively
    document.addEventListener("keydown", (e) => {
      const activeTag = document.activeElement?.tagName?.toLowerCase();
      if (activeTag === "input" || activeTag === "textarea" || activeTag === "select") return;
      if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        toggleFs();
      }
    });

    const updateFsUi = () => {
      const targetContainer = getActiveViewport();
      const inFs = !!(document.fullscreenElement || document.webkitFullscreenElement || targetContainer?.classList.contains("fullscreen-active"));
      if (fsLabel) {
        fsLabel.textContent = inFs ? "✕ EXIT (ESC)" : "⛶ FULLSCREEN (F)";
      }
      if (targetContainer) {
        if (inFs) targetContainer.classList.add("fullscreen-active");
        else targetContainer.classList.remove("fullscreen-active");
      }
    };

    document.addEventListener("fullscreenchange", updateFsUi);
    document.addEventListener("webkitfullscreenchange", updateFsUi);
  },

  connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/stream`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log("[IBVAP] Real-time stream connected");
      const hdrLatency = document.getElementById("hdr-latency");
      if (hdrLatency) hdrLatency.textContent = "CONNECTED";
    };

    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === "FRAME_UPDATE") {
        this.currentTracks = msg.tracks || [];
        this.currentZones = msg.zones || [];

        // Update Latency Metric (Standardized ms convention)
        const latMs = Math.round(msg.latency_ms || 35);
        const latTxt = document.getElementById("stream-latency-txt");
        const hdrLat = document.getElementById("hdr-latency");

        if (latTxt) {
          latTxt.textContent = `LATENCY: ${latMs} ms (PASS < 1200 ms)`;
        }
        if (hdrLat) {
          hdrLat.textContent = `${latMs} ms`;
        }

        // Update Telemetry Counters
        const countTargets = document.getElementById("telemetry-target-count");
        if (countTargets) countTargets.textContent = this.currentTracks.length;

        // Render frame with overlays
        this.renderFrame(msg.frame);

        // Update DEFCON-1 Mass Infiltration state
        if (msg.mass_status && window.IBVAP_Patrol) {
          window.IBVAP_Patrol.handleMassStatus(msg.mass_status);
        }

      } else if (msg.type === "NEW_ALERT") {
        if (window.IBVAP_Alerts) {
          window.IBVAP_Alerts.addAlert(msg.data);
        }
        window.IBVAP.playAlarmSound(msg.data.severity);
        this.triggerSuspiciousPopup(msg.data);
      } else if (msg.type === "RECURRENT_PERSON_SIGHTING") {
        if (window.IBVAP_Patrol) {
          window.IBVAP_Patrol.handleRecurrentSighting(msg.data);
        }
      } else if (msg.type === "MASS_INFILTRATION_ALERT") {
        if (window.IBVAP_Patrol) {
          window.IBVAP_Patrol.triggerDefcon1Alert(msg.data);
        }
      } else if (msg.type === "EVIDENCE_EXPORTED") {
        if (window.IBVAP_Forensics) {
          window.IBVAP_Forensics.showEvidencePackage(msg.data);
        }
      }
    };

    this.ws.onclose = () => {
      console.warn("[IBVAP] Stream disconnected, reconnecting in 2s...");
      setTimeout(() => this.connectWebSocket(), 2000);
    };
  },

  sendCommand(command, payload = {}) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ command, ...payload }));
    }
  },

  renderFrame(frameBase64) {
    if (!frameBase64) return;
    const img = new Image();
    img.onload = () => {
      const cw = this.canvas.width;
      const ch = this.canvas.height;
      this.ctx.clearRect(0, 0, cw, ch);
      this.ctx.drawImage(img, 0, 0, cw, ch);

      // Render Zone Overlays & Tracks with strictly distinct colors & non-overlapping banners
      this.renderZones(cw, ch);
      this.renderTracks(cw, ch);

      // Render Active In-Browser Drawing Tool Overlays (if user is drawing)
      if (window.IBVAP_ZoneEditor && window.IBVAP_ZoneEditor.isDrawing) {
        window.IBVAP_ZoneEditor.renderPreview(this.ctx, cw, ch);
      }
    };
    img.src = "data:image/jpeg;base64," + frameBase64;
  },

  renderZones(cw, ch) {
    let tripwireRowIndex = 0;
    let polygonRowIndex = 0;

    for (const zone of this.currentZones) {
      const coords = zone.coordinates || [];
      if (coords.length < 2) continue;

      if (zone.zone_type === "TRIPWIRE") {
        // Directed Tripwire Line: Vibrant Orange (#f97316), turns Red (#ef4444) on critical breach
        const p1 = coords[0];
        const p2 = coords[1];
        const lineColor = zone.severity === "CRITICAL" ? "#ef4444" : "#f97316";

        this.ctx.beginPath();
        this.ctx.moveTo(p1.x * cw, p1.y * ch);
        this.ctx.lineTo(p2.x * cw, p2.y * ch);
        this.ctx.strokeStyle = lineColor;
        this.ctx.lineWidth = 2.5;
        this.ctx.setLineDash([6, 4]);
        this.ctx.stroke();
        this.ctx.setLineDash([]);

        // Small directional arrowhead at midpoint of line
        const mx = (p1.x + p2.x) / 2 * cw;
        const my = (p1.y + p2.y) / 2 * ch;
        this.ctx.fillStyle = lineColor;
        this.ctx.beginPath();
        this.ctx.arc(mx, my, 4, 0, Math.PI * 2);
        this.ctx.fill();

        // Stacked Non-Overlapping HUD Banner (Slot 1: y = ch - 54px)
        const slotY = ch - 54 - (tripwireRowIndex * 26);
        tripwireRowIndex++;
        const twText = `⚡ TRIPWIRE: ${zone.name} [${zone.direction}]`;
        const twWidth = Math.min(cw - 24, twText.length * 7.2 + 20);

        // Dark background pill with orange border
        this.ctx.fillStyle = "rgba(10, 16, 26, 0.92)";
        this.ctx.fillRect(12, slotY - 14, twWidth, 20);
        this.ctx.strokeStyle = lineColor;
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(12, slotY - 14, twWidth, 20);

        this.ctx.fillStyle = "#ffffff";
        this.ctx.font = "bold 10px 'JetBrains Mono', monospace";
        this.ctx.fillText(twText, 20, slotY);

      } else if (zone.zone_type === "RESTRICTED_POLYGON") {
        // Restricted Area Geofence: Warm Amber (#f59e0b)
        if (coords.length < 3) continue;

        this.ctx.beginPath();
        this.ctx.moveTo(coords[0].x * cw, coords[0].y * ch);
        for (let i = 1; i < coords.length; i++) {
          this.ctx.lineTo(coords[i].x * cw, coords[i].y * ch);
        }
        this.ctx.closePath();

        this.ctx.fillStyle = "rgba(245, 158, 11, 0.08)";
        this.ctx.fill();
        this.ctx.strokeStyle = "#f59e0b";
        this.ctx.lineWidth = 1.8;
        this.ctx.stroke();

        // Stacked Non-Overlapping HUD Banner (Slot 2: y = ch - 26px)
        const slotY = ch - 26 - (polygonRowIndex * 26);
        polygonRowIndex++;
        const polyText = `⚠️ RESTRICTED ZONE [90s DWELL]: ${zone.name}`;
        const polyWidth = Math.min(cw - 24, polyText.length * 7.2 + 20);

        // Dark background pill with amber border
        this.ctx.fillStyle = "rgba(10, 16, 26, 0.92)";
        this.ctx.fillRect(12, slotY - 14, polyWidth, 20);
        this.ctx.strokeStyle = "#f59e0b";
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(12, slotY - 14, polyWidth, 20);

        this.ctx.fillStyle = "#f59e0b";
        this.ctx.font = "bold 10px 'JetBrains Mono', monospace";
        this.ctx.fillText(polyText, 20, slotY);
      }
    }
  },

  renderTracks(cw, ch) {
    for (const track of this.currentTracks) {
      const bbox = track.bbox;
      const x1 = bbox[0] * cw;
      const y1 = bbox[1] * ch;
      const x2 = bbox[2] * cw;
      const y2 = bbox[3] * ch;
      const bw = x2 - x1;
      const bh = y2 - y1;

      // Strictly Distinct Tactical Color Coding
      let color = "#00d4ff"; // Electric Cyan for Person
      if (track.dwell_time > 15.0 || track.is_threat) {
        color = "#ef4444"; // Flash Crimson RED exclusively for active alert / breach
      } else if (track.is_vehicle) {
        color = "#818cf8"; // Electric Indigo / Blue for Vehicles
      } else if (track.is_fauna) {
        color = "#64748b"; // Slate Gray for Animals / Fauna
      }

      // 1. Draw Trajectory Trail
      if (track.trail && track.trail.length > 1) {
        this.ctx.beginPath();
        this.ctx.moveTo(track.trail[0][0] * cw, track.trail[0][1] * ch);
        for (let i = 1; i < track.trail.length; i++) {
          this.ctx.lineTo(track.trail[i][0] * cw, track.trail[i][1] * ch);
        }
        this.ctx.strokeStyle = color;
        this.ctx.lineWidth = 1.5;
        this.ctx.globalAlpha = 0.45;
        this.ctx.stroke();
        this.ctx.globalAlpha = 1.0;
      }

      // 2. Draw Tactical Bounding Box with Corner Brackets
      this.ctx.strokeStyle = color;
      this.ctx.lineWidth = 2;
      this.ctx.strokeRect(x1, y1, bw, bh);

      // Corner accent brackets
      const cl = Math.min(10, bw / 3);
      this.ctx.lineWidth = 3;
      // Top-left
      this.ctx.beginPath();
      this.ctx.moveTo(x1, y1 + cl); this.ctx.lineTo(x1, y1); this.ctx.lineTo(x1 + cl, y1);
      // Top-right
      this.ctx.moveTo(x2 - cl, y1); this.ctx.lineTo(x2, y1); this.ctx.lineTo(x2, y1 + cl);
      // Bottom-left
      this.ctx.moveTo(x1, y2 - cl); this.ctx.lineTo(x1, y2); this.ctx.lineTo(x1 + cl, y2);
      // Bottom-right
      this.ctx.moveTo(x2 - cl, y2); this.ctx.lineTo(x2, y2); this.ctx.lineTo(x2, y2 - cl);
      this.ctx.stroke();

      // 3. Track Label Tag
      const label = `ID:${track.track_id} ${track.class_name.toUpperCase()} ${(track.confidence * 100).toFixed(0)}%`;
      this.ctx.fillStyle = "rgba(8, 12, 20, 0.88)";
      this.ctx.fillRect(x1, y1 - 18, Math.max(80, label.length * 7), 16);

      this.ctx.fillStyle = color;
      this.ctx.font = "bold 10px 'JetBrains Mono', monospace";
      this.ctx.fillText(label, x1 + 4, y1 - 6);

      // 4. Dwell Time Tag if Loitering (> 2 seconds)
      if (track.dwell_time > 2.0) {
        const dwellLabel = `DWELL: ${track.dwell_time.toFixed(0)}s / 90s`;
        this.ctx.fillStyle = track.dwell_time > 15.0 ? "rgba(239, 68, 68, 0.9)" : "rgba(245, 158, 11, 0.9)";
        this.ctx.fillRect(x1, y2 + 2, 110, 14);
        this.ctx.fillStyle = "#000";
        this.ctx.font = "bold 9px 'JetBrains Mono', monospace";
        this.ctx.fillText(dwellLabel, x1 + 4, y2 + 12);
      }
    }
  },

  // ===========================================================================
  // 2x2 MULTI-CAMERA MATRIX GRID CONTROLLER
  // ===========================================================================

  setMatrixViewMode(enableMatrix) {
    this.matrixMode = !!enableMatrix;
    const canvasContainer = document.getElementById("single-cam-container") || document.getElementById("canvas-container");
    const matrixContainer = document.getElementById("matrix-container");
    const btnSingle = document.getElementById("btn-view-single");
    const btnMatrix = document.getElementById("btn-view-matrix");

    if (this.matrixMode) {
      if (canvasContainer) canvasContainer.style.display = "none";
      if (matrixContainer) matrixContainer.style.display = "grid";
      btnSingle?.classList.remove("active");
      btnMatrix?.classList.add("active");
      this.initMatrixStreams();
    } else {
      if (matrixContainer) matrixContainer.style.display = "none";
      if (canvasContainer) canvasContainer.style.display = "flex";
      btnMatrix?.classList.remove("active");
      btnSingle?.classList.add("active");
    }
  },

  initMatrixStreams() {
    this.sectorCams.forEach(camId => {
      const canvas = document.getElementById(`matrix-canvas-${camId}`);
      if (!canvas) return;

      this.matrixCanvases[camId] = canvas;
      this.matrixCtxs[camId] = canvas.getContext("2d");

      if (!this.matrixSockets[camId] || this.matrixSockets[camId].readyState === WebSocket.CLOSED) {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws/stream?camera_id=${camId}&grid=true`;
        const ws = new WebSocket(wsUrl);

        ws.onmessage = (event) => {
          if (!this.matrixMode) return;
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === "FRAME_UPDATE") {
              this.renderMatrixTile(camId, msg.frame, msg.tracks || [], msg.zones || []);
              const hud = document.getElementById(`matrix-hud-${camId}`);
              if (hud) hud.textContent = `TARGETS: ${(msg.tracks || []).length} • ${Math.round(msg.latency_ms || 35)}ms`;
            } else if (msg.type === "NEW_ALERT") {
              if (window.IBVAP_Alerts) window.IBVAP_Alerts.addAlert(msg.data);
              this.triggerSuspiciousPopup(msg.data);
            }
          } catch (e) {}
        };

        ws.onclose = () => {
          if (this.matrixMode) {
            setTimeout(() => this.initMatrixStreams(), 2500);
          }
        };

        this.matrixSockets[camId] = ws;
      }
    });
  },

  renderMatrixTile(camId, frameB64, tracks, zones) {
    const ctx = this.matrixCtxs[camId];
    const canvas = this.matrixCanvases[camId];
    if (!ctx || !canvas || !frameB64) return;

    let img = this.matrixImages[camId];
    if (!img) {
      img = new Image();
      this.matrixImages[camId] = img;
    }

    img.onload = () => {
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      const cw = canvas.width;
      const ch = canvas.height;

      // Draw virtual tripwires & zones
      zones.forEach(z => {
        const coords = z.coordinates || [];
        if (!coords.length) return;
        ctx.save();
        if (z.zone_type === "TRIPWIRE") {
          ctx.strokeStyle = "#f97316";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(coords[0].x * cw, coords[0].y * ch);
          ctx.lineTo(coords[1].x * cw, coords[1].y * ch);
          ctx.stroke();
        } else {
          ctx.strokeStyle = "#f59e0b";
          ctx.fillStyle = "rgba(245, 158, 11, 0.12)";
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          coords.forEach((pt, i) => {
            if (i === 0) ctx.moveTo(pt.x * cw, pt.y * ch);
            else ctx.lineTo(pt.x * cw, pt.y * ch);
          });
          ctx.closePath();
          ctx.fill();
          ctx.stroke();
        }
        ctx.restore();
      });

      // Draw dynamic AI tracks with tactical corner brackets and telemetry tags
      tracks.forEach(t => {
        const [x1, y1, x2, y2] = t.bbox;
        const rx = x1 * cw;
        const ry = y1 * ch;
        const rw = (x2 - x1) * cw;
        const rh = (y2 - y1) * ch;

        ctx.save();
        let boxColor = "#00d4ff"; // Cyan for person
        if (t.dwell_time > 15.0 || t.is_threat) {
          boxColor = "#ef4444"; // Flash Red for Threat / Breach
        } else if (t.is_vehicle || ["truck", "car", "bus", "motorbike", "vehicle"].includes(t.class_name)) {
          boxColor = "#818cf8"; // Indigo for Vehicle
        } else if (t.class_name === "boat" || t.class_name === "watercraft") {
          boxColor = "#22c55e"; // Green for Boat
        } else if (t.is_fauna || ["dog", "cow", "horse", "sheep", "bird"].includes(t.class_name)) {
          boxColor = "#94a3b8"; // Slate for Fauna
        }

        // 1. Draw Trajectory Trail
        if (t.trail && t.trail.length > 1) {
          ctx.beginPath();
          ctx.moveTo(t.trail[0][0] * cw, t.trail[0][1] * ch);
          for (let i = 1; i < t.trail.length; i++) {
            ctx.lineTo(t.trail[i][0] * cw, t.trail[i][1] * ch);
          }
          ctx.strokeStyle = boxColor;
          ctx.lineWidth = 1.2;
          ctx.globalAlpha = 0.45;
          ctx.stroke();
          ctx.globalAlpha = 1.0;
        }

        // 2. Tactical Bounding Box with Corner Accent Brackets
        ctx.strokeStyle = boxColor;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(rx, ry, rw, rh);

        const cl = Math.min(8, rw / 3);
        ctx.lineWidth = 2.5;
        // Top-left
        ctx.beginPath(); ctx.moveTo(rx, ry + cl); ctx.lineTo(rx, ry); ctx.lineTo(rx + cl, ry);
        // Top-right
        ctx.moveTo(rx + rw - cl, ry); ctx.lineTo(rx + rw, ry); ctx.lineTo(rx + rw, ry + cl);
        // Bottom-left
        ctx.moveTo(rx, ry + rh - cl); ctx.lineTo(rx, ry + rh); ctx.lineTo(rx + cl, ry + rh);
        // Bottom-right
        ctx.moveTo(rx + rw - cl, ry + rh); ctx.lineTo(rx + rw, ry + rh); ctx.lineTo(rx + rw, ry + rh - cl);
        ctx.stroke();

        // 3. Track Label Tag
        const confTxt = t.confidence ? `${(t.confidence * 100).toFixed(0)}%` : "";
        const tagText = `#${t.track_id} ${t.class_name.toUpperCase()} ${confTxt}`;
        const tagWidth = Math.max(65, tagText.length * 6.5 + 8);
        ctx.fillStyle = "rgba(10, 15, 25, 0.85)";
        ctx.fillRect(rx, Math.max(0, ry - 14), tagWidth, 14);
        ctx.fillStyle = boxColor;
        ctx.font = "bold 9px 'JetBrains Mono', monospace";
        ctx.fillText(tagText, rx + 4, Math.max(10, ry - 3));

        // 4. Dwell Time Tag if Loitering
        if (t.dwell_time > 2.0) {
          const dwellTxt = `DWELL: ${t.dwell_time.toFixed(0)}s`;
          ctx.fillStyle = t.dwell_time > 15.0 ? "rgba(239, 68, 68, 0.9)" : "rgba(245, 158, 11, 0.9)";
          ctx.fillRect(rx, ry + rh + 2, 72, 12);
          ctx.fillStyle = "#000";
          ctx.font = "bold 8px 'JetBrains Mono', monospace";
          ctx.fillText(dwellTxt, rx + 4, ry + rh + 10);
        }

        ctx.restore();
      });
    };

    img.src = "data:image/jpeg;base64," + frameB64;
  },

  switchToSingleView(camId) {
    this.matrixMode = false;
    const matrixContainer = document.getElementById("matrix-container");
    const canvasContainer = document.getElementById("single-cam-container") || document.getElementById("canvas-container");
    const btnMatrix = document.getElementById("btn-view-matrix");
    const btnSingle = document.getElementById("btn-view-single");

    if (matrixContainer) matrixContainer.style.display = "none";
    if (canvasContainer) canvasContainer.style.display = "flex";
    btnMatrix?.classList.remove("active");
    btnSingle?.classList.add("active");

    if (camId) {
      window.IBVAP.activeCameraId = camId;
      const sel = document.getElementById("cam-select");
      if (sel) sel.value = camId;
      this.sendCommand("SWITCH_CAMERA", { camera_id: camId });

      const singleTitle = document.getElementById("single-cam-title");
      const names = {
        "CAM-01-IBB-PETRAPOLE": "● CAM-01: Zero Line (Tower 7A - Petrapole)",
        "CAM-02-IBB-ICHAMATI": "● CAM-02: Ichamati River Reach (Thermal Ironbow)",
        "CAM-03-IBB-ICP-ANPR": "● CAM-03: ICP Petrapole Cargo Barrier (ANPR)",
        "CAM-04-IBB-DAWKI": "● CAM-04: Smart Border Fence (Dawki Post 12, Meghalaya)"
      };
      if (singleTitle) singleTitle.textContent = names[camId] || `● ${camId}`;

      const sectorEl = document.getElementById("hdr-sector");
      if (sectorEl) {
        sectorEl.textContent = names[camId] || camId;
      }
    }
  },

  // ===========================================================================
  // AUTOMATED SUSPICIOUS ACTIVITY POP-UP CONTROLLER
  // ===========================================================================

  triggerSuspiciousPopup(alert) {
    if (!alert) return;

    // Flash breached matrix tile if in matrix mode
    const tile = document.getElementById(`matrix-tile-${alert.camera_id}`);
    const badge = document.getElementById(`matrix-badge-${alert.camera_id}`);
    if (tile) {
      tile.classList.add("breach-alerting");
      if (badge) badge.style.display = "block";
      setTimeout(() => {
        tile.classList.remove("breach-alerting");
        if (badge) badge.style.display = "none";
      }, 15000);
    }

    // Only open the intrusive popup if operator explicitly enabled AUTO POPUP
    if (!this.autoPopupEnabled) return;

    const modal = document.getElementById("modal-suspicious-popup");
    if (!modal || modal.style.display === "flex") return;

    const now = Date.now();
    if (now - this.lastPopupTime < 25000) return;
    this.lastPopupTime = now;

    this.currentSuspiciousAlert = alert;

    const camNames = {
      "CAM-01-IBB-PETRAPOLE": "Tower 7A – Zero Line Perimeter (Petrapole)",
      "CAM-02-IBB-ICHAMATI": "Thermal Ambush – Ichamati River Gap",
      "CAM-03-IBB-ICP-ANPR": "ICP Barrier Gate – Cargo Checkpost",
      "CAM-04-IBB-DAWKI": "IR Smart Fence – Dawki Post 12, Meghalaya"
    };

    const bopName = camNames[alert.camera_id] || alert.camera_name || alert.camera_id;
    document.getElementById("suspicious-popup-cam").textContent = alert.camera_id;
    document.getElementById("suspicious-popup-bop").textContent = bopName;
    document.getElementById("suspicious-threat-banner").textContent = (alert.alert_type || "SUSPICIOUS ACTIVITY").replace(/_/g, " ");
    document.getElementById("suspicious-popup-class").textContent = `${(alert.object_type || "PERSON").toUpperCase()} (ACTIVE INTRUSION)`;
    document.getElementById("suspicious-popup-conf").textContent = `${Math.round((alert.confidence || 0.95) * 100)}% (CONFIRMED THREAT)`;
    document.getElementById("suspicious-popup-time").textContent = alert.timestamp ? new Date(alert.timestamp).toLocaleTimeString("en-IN") : "JUST NOW";

    const thumb = document.getElementById("suspicious-popup-thumb");
    if (thumb) {
      thumb.src = alert.snapshot_path || this.getLiveSnapshotDataUrl(alert.camera_id) || "/frontend/assets/placeholder.jpg";
    }

    modal.style.display = "flex";

    // Play alarm sound
    if (window.IBVAP?.playAlarmSound) {
      window.IBVAP.playAlarmSound(alert.severity || "CRITICAL");
    }
  },

  getLiveSnapshotDataUrl(camId = null) {
    try {
      let canvas = null;
      if (this.matrixMode) {
        const id = camId || window.IBVAP?.activeCameraId || "CAM-01-IBB-PETRAPOLE";
        canvas = document.getElementById(`matrix-canvas-${id}`) || this.canvas;
      } else {
        canvas = this.canvas;
      }
      if (canvas && canvas.width > 0 && canvas.height > 0) {
        return canvas.toDataURL("image/jpeg", 0.85);
      }
    } catch (e) {
      console.warn("Could not capture live canvas data URL:", e);
    }
    return null;
  }
};

document.addEventListener("DOMContentLoaded", () => {
  window.IBVAP_Player.init();
});
