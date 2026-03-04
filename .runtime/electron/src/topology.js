/**
 * KnowledgeStarMap — Canvas-based knowledge star map for MUSEON Dashboard.
 * Pure vanilla JS, no imports. Loaded via <script> before app.js.
 *
 * Features:
 * - 3D orbital rotation with perspective projection
 * - Mouse drag to rotate (not pan) for immersive interaction
 * - Node brightness = ri_score (proficiency)
 * - Nodes orbit tightly around a shared center
 * - Link brightness = average ri_score of both ends
 * - Color coding by crystal type
 * - Ambient floating particles for cosmic atmosphere
 * - Scroll to zoom
 */
(function () {
  "use strict";

  var CRYSTAL_COLORS = {
    Insight: "#60a5fa",
    Pattern: "#34d399",
    Lesson: "#fbbf24",
    Hypothesis: "#a78bfa"
  };

  var LINK_COLORS = {
    supports:    { color: "#94a3b8", dash: [],     baseAlpha: 0.525 },
    contradicts: { color: "#ef4444", dash: [6, 4], baseAlpha: 0.825 },
    extends:     { color: "#34d399", dash: [],     baseAlpha: 0.675 },
    related:     { color: "#64748b", dash: [],     baseAlpha: 0.225 }
  };

  var ROTATION_SPEED = 0.0006; // radians per frame (2x original)
  var PARTICLE_COUNT = 30;
  var PERSPECTIVE = 600; // perspective distance for 3D projection

  function KnowledgeStarMap(canvasElement) {
    this.canvas = canvasElement;
    this.ctx = canvasElement.getContext("2d");
    this.dpr = window.devicePixelRatio || 1;
    this.width = canvasElement.clientWidth;
    this.height = canvasElement.clientHeight;
    this.crystals = [];
    this.links = [];
    this.nodes = [];
    this._nodeMap = {};
    this.camera = { zoom: 1 };
    // 3D rotation angles (controlled by auto-rotation + mouse drag)
    this._rotY = 0;  // rotation around Y axis (left-right)
    this._rotX = 0.3; // slight tilt for 3D depth feel
    this._autoRotY = 0; // auto rotation accumulator
    this._dragging = false;
    this._dragStart = { x: 0, y: 0 };
    this._dragRotStart = { x: 0, y: 0 };
    this._hoverNode = null;
    this._tooltip = null;
    this._bound = {};
    this._animFrame = null;
    this._time = 0;
    this._particles = [];
    this._initCanvas();
    this._initParticles();
    this._initEvents();
    this._startAnimation();
  }

  KnowledgeStarMap.prototype._initCanvas = function () {
    this.canvas.width = this.width * this.dpr;
    this.canvas.height = this.height * this.dpr;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  };

  KnowledgeStarMap.prototype.resize = function (w, h) {
    this.width = w;
    this.height = h;
    this._initCanvas();
  };

  /* ---- 3D Projection ---- */
  KnowledgeStarMap.prototype._project = function (x3d, y3d, z3d) {
    // Apply Y rotation (horizontal spin)
    var cosY = Math.cos(this._rotY + this._autoRotY);
    var sinY = Math.sin(this._rotY + this._autoRotY);
    var rx = x3d * cosY - z3d * sinY;
    var rz = x3d * sinY + z3d * cosY;
    var ry = y3d;

    // Apply X rotation (vertical tilt)
    var cosX = Math.cos(this._rotX);
    var sinX = Math.sin(this._rotX);
    var ry2 = ry * cosX - rz * sinX;
    var rz2 = ry * sinX + rz * cosX;

    // Perspective projection
    var scale = PERSPECTIVE / (PERSPECTIVE + rz2);
    var cx = this.width / 2;
    var cy = this.height / 2;
    return {
      x: cx + rx * scale * this.camera.zoom,
      y: cy + ry2 * scale * this.camera.zoom,
      scale: scale,
      z: rz2
    };
  };

  /* ---- Ambient Particles ---- */
  KnowledgeStarMap.prototype._initParticles = function () {
    this._particles = [];
    for (var i = 0; i < PARTICLE_COUNT; i++) {
      this._particles.push({
        x: Math.random() * this.width,
        y: Math.random() * this.height,
        r: 0.5 + Math.random() * 1.2,
        alpha: 0.05 + Math.random() * 0.12,
        vx: (Math.random() - 0.5) * 0.15,
        vy: (Math.random() - 0.5) * 0.15,
        phase: Math.random() * Math.PI * 2
      });
    }
  };

  /* ---- Animation Loop ---- */
  KnowledgeStarMap.prototype._startAnimation = function () {
    var self = this;
    function loop() {
      self._time += 0.016;
      // Auto-resize if canvas dimensions changed or were 0 at init
      var cw = self.canvas.clientWidth || self.canvas.parentElement?.clientWidth || 400;
      var ch = self.canvas.clientHeight || self.canvas.parentElement?.clientHeight || 300;
      if (cw > 0 && ch > 0 && (cw !== self.width || ch !== self.height)) {
        self.width = cw;
        self.height = ch;
        self._initCanvas();
        if (self._particles.length === 0 || self._particles[0].x > cw * 2) {
          self._initParticles();
        }
      }
      self._update();
      self._draw();
      self._animFrame = requestAnimationFrame(loop);
    }
    loop();
  };

  KnowledgeStarMap.prototype._update = function () {
    // Update particles (always, even with 0 nodes)
    for (var p = 0; p < this._particles.length; p++) {
      var pt = this._particles[p];
      pt.x += pt.vx;
      pt.y += pt.vy;
      if (pt.x < 0) pt.x = this.width;
      if (pt.x > this.width) pt.x = 0;
      if (pt.y < 0) pt.y = this.height;
      if (pt.y > this.height) pt.y = 0;
    }
    // Auto rotation around Y axis (continuous slow spin)
    if (!this._dragging) {
      this._autoRotY += ROTATION_SPEED;
    }
  };

  /* ---- Events ---- */
  KnowledgeStarMap.prototype._initEvents = function () {
    var self = this;
    this._bound.onWheel = function (e) { self._onWheel(e); };
    this._bound.onMouseDown = function (e) { self._onMouseDown(e); };
    this._bound.onMouseMove = function (e) { self._onMouseMove(e); };
    this._bound.onMouseUp = function (e) { self._onMouseUp(e); };
    this.canvas.addEventListener("wheel", this._bound.onWheel, { passive: false });
    this.canvas.addEventListener("mousedown", this._bound.onMouseDown);
    this.canvas.addEventListener("mousemove", this._bound.onMouseMove);
    this.canvas.addEventListener("mouseup", this._bound.onMouseUp);
    // Also catch mouseup outside canvas
    this._bound.onMouseUpGlobal = function (e) { self._onMouseUp(e); };
    document.addEventListener("mouseup", this._bound.onMouseUpGlobal);
  };

  KnowledgeStarMap.prototype._onWheel = function (e) {
    e.preventDefault();
    var factor = e.deltaY < 0 ? 1.1 : 0.9;
    this.camera.zoom = Math.max(0.3, Math.min(5, this.camera.zoom * factor));
  };

  KnowledgeStarMap.prototype._onMouseDown = function (e) {
    this._dragging = true;
    this._dragStart = { x: e.clientX, y: e.clientY };
    this._dragRotStart = { x: this._rotX, y: this._rotY };
    this.canvas.style.cursor = "grabbing";
  };

  KnowledgeStarMap.prototype._onMouseMove = function (e) {
    if (this._dragging) {
      var dx = e.clientX - this._dragStart.x;
      var dy = e.clientY - this._dragStart.y;
      // Drag rotates the 3D scene
      this._rotY = this._dragRotStart.y + dx * 0.005;
      this._rotX = Math.max(-1.2, Math.min(1.2,
        this._dragRotStart.x + dy * 0.005));
      return;
    }
    // Hover detection using projected coordinates
    var rect = this.canvas.getBoundingClientRect();
    var mx = e.clientX - rect.left;
    var my = e.clientY - rect.top;
    var found = null;
    for (var i = 0; i < this.nodes.length; i++) {
      var n = this.nodes[i];
      var proj = this._project(n.x3d, n.y3d, n.z3d);
      var hitR = (n.r * proj.scale * this.camera.zoom) + 5;
      var ddx = mx - proj.x, ddy = my - proj.y;
      if (ddx * ddx + ddy * ddy < hitR * hitR) { found = n; break; }
    }
    if (found !== this._hoverNode) {
      this._hoverNode = found;
      this.canvas.style.cursor = found ? "pointer" : "grab";
      this._updateTooltip(e);
    }
    if (found) this._updateTooltip(e);
  };

  KnowledgeStarMap.prototype._onMouseUp = function () {
    this._dragging = false;
    this.canvas.style.cursor = "grab";
  };

  KnowledgeStarMap.prototype._updateTooltip = function (e) {
    if (!this._hoverNode) {
      if (this._tooltip) { this._tooltip.remove(); this._tooltip = null; }
      return;
    }
    if (!this._tooltip) {
      this._tooltip = document.createElement("div");
      this._tooltip.style.cssText = "position:fixed;padding:8px 14px;background:rgba(13,20,36,0.95);color:#e2e8f0;border:1px solid #334155;border-radius:10px;font-size:12px;pointer-events:none;z-index:9999;max-width:260px;line-height:1.5;backdrop-filter:blur(12px);box-shadow:0 4px 20px rgba(0,0,0,0.4);";
      document.body.appendChild(this._tooltip);
    }
    var n = this._hoverNode;
    var typeZh = { Insight: '\u6D1E\u898B', Pattern: '\u6A21\u5F0F', Lesson: '\u7D93\u9A57', Hypothesis: '\u5047\u8AAC' };
    this._tooltip.innerHTML = "<strong>" + (n.summary || n.cuid) + "</strong><br><span style='color:" + n.color + "'>\u25CF " + (typeZh[n.type] || n.type) + "</span> \u00B7 \u5171\u632F " + n.ri.toFixed(2);
    this._tooltip.style.left = (e.clientX + 14) + "px";
    this._tooltip.style.top = (e.clientY + 14) + "px";
  };

  /* ---- Data ---- */
  KnowledgeStarMap.prototype.setData = function (crystals, crystalLinks) {
    this.crystals = crystals || [];
    this.links = crystalLinks || [];
    if (this.crystals.length === 0) { this.nodes = []; this._nodeMap = {}; return; }
    this._buildNodes();
    this._runForceLayout(150);
  };

  KnowledgeStarMap.prototype._buildNodes = function () {
    // Place nodes in 3D space (spherical distribution around origin)
    var spread = Math.min(this.width, this.height) * 0.25;
    this.nodes = [];
    for (var i = 0; i < this.crystals.length; i++) {
      var c = this.crystals[i];
      var ri = c.ri_score || 0;
      var r = 1 + ri * 3.5;
      var now = Date.now();
      var ref = c.last_referenced ? new Date(c.last_referenced).getTime() : 0;
      var recent = (now - ref) < 86400000;

      // Spherical initial placement (tighter cluster)
      var phi = Math.acos(1 - 2 * (i + 0.5) / this.crystals.length);
      var theta = Math.PI * (1 + Math.sqrt(5)) * i; // golden angle
      var radius = spread * (0.4 + Math.random() * 0.6);
      this.nodes.push({
        x3d: radius * Math.sin(phi) * Math.cos(theta),
        y3d: radius * Math.sin(phi) * Math.sin(theta) * 0.7, // flatten Y for aesthetics
        z3d: radius * Math.cos(phi),
        vx: 0, vy: 0, vz: 0, r: r,
        cuid: c.cuid,
        type: c.crystal_type,
        color: CRYSTAL_COLORS[c.crystal_type] || "#94a3b8",
        summary: c.g1_summary || "",
        ri: ri,
        recent: recent,
        phase: Math.random() * Math.PI * 2
      });
    }
    this._nodeMap = {};
    for (var j = 0; j < this.nodes.length; j++) {
      this._nodeMap[this.nodes[j].cuid] = this.nodes[j];
    }
  };

  /* ---- Force-directed layout (3D) ---- */
  KnowledgeStarMap.prototype._runForceLayout = function (iterations) {
    var nodes = this.nodes, links = this.links, map = this._nodeMap;
    var repulse = 600;
    var stiffness = 0.05;
    // Stronger gravity to keep nodes clustered tightly
    var gravity = 0.04 / Math.max(1, nodes.length / 15);
    var damping = 0.82;
    var restLength = 30;

    for (var iter = 0; iter < iterations; iter++) {
      var i, j, n, m, dx, dy, dz, dist, force, fx, fy, fz;
      // Repulsion (3D)
      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        for (j = i + 1; j < nodes.length; j++) {
          m = nodes[j];
          dx = n.x3d - m.x3d; dy = n.y3d - m.y3d; dz = n.z3d - m.z3d;
          dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
          force = repulse / (dist * dist);
          fx = (dx / dist) * force; fy = (dy / dist) * force; fz = (dz / dist) * force;
          n.vx += fx; n.vy += fy; n.vz += fz;
          m.vx -= fx; m.vy -= fy; m.vz -= fz;
        }
      }
      // Springs (3D)
      for (i = 0; i < links.length; i++) {
        var a = map[links[i].from_cuid], b = map[links[i].to_cuid];
        if (!a || !b) continue;
        dx = b.x3d - a.x3d; dy = b.y3d - a.y3d; dz = b.z3d - a.z3d;
        dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
        force = (dist - restLength) * stiffness;
        fx = (dx / dist) * force; fy = (dy / dist) * force; fz = (dz / dist) * force;
        a.vx += fx; a.vy += fy; a.vz += fz;
        b.vx -= fx; b.vy -= fy; b.vz -= fz;
      }
      // Gravity toward origin (3D)
      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        n.vx -= n.x3d * gravity;
        n.vy -= n.y3d * gravity;
        n.vz -= n.z3d * gravity;
      }
      // Integrate + damping
      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        n.vx *= damping; n.vy *= damping; n.vz *= damping;
        n.x3d += n.vx; n.y3d += n.vy; n.z3d += n.vz;
      }
    }
  };

  /* ---- Drawing ---- */
  KnowledgeStarMap.prototype._draw = function () {
    var ctx = this.ctx, w = this.width, h = this.height, t = this._time;
    ctx.clearRect(0, 0, w, h);

    // Draw ambient particles (screen space)
    this._drawAmbientParticles(ctx, t);

    if (this.nodes.length === 0) {
      this._drawEmptyState(ctx, w, h, t);
    } else {
      // Project all nodes to 2D, sort by depth for painter's algorithm
      var projected = [];
      for (var i = 0; i < this.nodes.length; i++) {
        var n = this.nodes[i];
        // Gentle float offset in 3D
        var floatX = Math.sin(t * 0.5 + n.phase) * 1.5;
        var floatY = Math.cos(t * 0.3 + n.phase * 1.3) * 1.5;
        var proj = this._project(n.x3d + floatX, n.y3d + floatY, n.z3d);
        projected.push({ node: n, proj: proj });
      }
      // Sort far to near (draw back nodes first)
      projected.sort(function (a, b) { return b.proj.z - a.proj.z; });

      this._drawLinks(ctx, t);
      this._drawProjectedNodes(ctx, t, projected);
    }
  };

  /* ---- Ambient Particles ---- */
  KnowledgeStarMap.prototype._drawAmbientParticles = function (ctx, t) {
    for (var i = 0; i < this._particles.length; i++) {
      var p = this._particles[i];
      var twinkle = 0.5 + 0.5 * Math.sin(t * 0.8 + p.phase);
      ctx.fillStyle = "#e2e8f0";
      ctx.globalAlpha = p.alpha * twinkle;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  };

  /* ---- Empty State ---- */
  KnowledgeStarMap.prototype._drawEmptyState = function (ctx, w, h, t) {
    var cx = w / 2, cy = h / 2;
    var pulse = 1 + Math.sin(t * 1.2) * 0.3;
    var r = 12 * pulse;

    var grad = ctx.createRadialGradient(cx, cy, r * 0.3, cx, cy, r * 4);
    grad.addColorStop(0, "rgba(201,169,110,0.15)");
    grad.addColorStop(1, "rgba(201,169,110,0)");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, r * 4, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "#c9a96e";
    ctx.globalAlpha = 0.4 + Math.sin(t * 1.2) * 0.2;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;

    ctx.fillStyle = "#6b5f4a";
    ctx.font = "12px -apple-system, BlinkMacSystemFont, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("\u77E5\u8B58\u661F\u5716\u5373\u5C07\u8A95\u751F", cx, cy + 35);
  };

  /* ---- Draw Links (3D projected) ---- */
  KnowledgeStarMap.prototype._drawLinks = function (ctx, t) {
    var map = this._nodeMap;
    for (var i = 0; i < this.links.length; i++) {
      var link = this.links[i];
      var a = map[link.from_cuid], b = map[link.to_cuid];
      if (!a || !b) continue;
      var style = LINK_COLORS[link.link_type] || LINK_COLORS.related;
      var avgRi = ((a.ri || 0) + (b.ri || 0)) / 2;
      var alpha = style.baseAlpha * (0.2 + avgRi * 0.8);
      var lineW = 0.5 + avgRi * 2;

      // Project link endpoints
      var pa = this._project(a.x3d, a.y3d, a.z3d);
      var pb = this._project(b.x3d, b.y3d, b.z3d);

      // Depth-based fade (further = dimmer)
      var depthFade = Math.min(1, (pa.scale + pb.scale) / 2);
      ctx.strokeStyle = style.color;
      ctx.globalAlpha = alpha * depthFade;
      ctx.lineWidth = lineW * depthFade;
      ctx.setLineDash(style.dash);
      ctx.beginPath();
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
  };

  /* ---- Draw Nodes (depth-sorted) ---- */
  KnowledgeStarMap.prototype._drawProjectedNodes = function (ctx, t, projected) {
    for (var i = 0; i < projected.length; i++) {
      var n = projected[i].node;
      var proj = projected[i].proj;
      var drawX = proj.x;
      var drawY = proj.y;
      var depthScale = proj.scale;
      var nodeR = n.r * depthScale * this.camera.zoom;

      // Depth-based alpha (further = dimmer, closer = brighter)
      var depthAlpha = Math.max(0.3, Math.min(1.0, depthScale));

      // Glow for recently referenced nodes
      if (n.recent) {
        var glow = ctx.createRadialGradient(drawX, drawY, nodeR * 0.5, drawX, drawY, nodeR * 3.5);
        glow.addColorStop(0, n.color + "35");
        glow.addColorStop(1, n.color + "00");
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(drawX, drawY, nodeR * 3.5, 0, Math.PI * 2);
        ctx.fill();
      }

      // Outer subtle aura
      var aura = ctx.createRadialGradient(drawX, drawY, nodeR, drawX, drawY, nodeR * 2);
      aura.addColorStop(0, n.color + "15");
      aura.addColorStop(1, n.color + "00");
      ctx.fillStyle = aura;
      ctx.beginPath();
      ctx.arc(drawX, drawY, nodeR * 2, 0, Math.PI * 2);
      ctx.fill();

      // Core circle — brightness driven by ri_score * depth
      ctx.fillStyle = n.color;
      ctx.globalAlpha = (0.3 + n.ri * 0.7) * depthAlpha;
      ctx.beginPath();
      ctx.arc(drawX, drawY, nodeR, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;

      // Hover highlight
      if (n === this._hoverNode) {
        ctx.strokeStyle = "#f3ede0";
        ctx.lineWidth = 1.5;
        ctx.globalAlpha = 0.8;
        ctx.beginPath();
        ctx.arc(drawX, drawY, nodeR + 4, 0, Math.PI * 2);
        ctx.stroke();
        ctx.globalAlpha = 1;

        this._highlightConnected(ctx, n);
      }
    }
  };

  /* ---- Highlight connected nodes on hover ---- */
  KnowledgeStarMap.prototype._highlightConnected = function (ctx, node) {
    var map = this._nodeMap;
    for (var i = 0; i < this.links.length; i++) {
      var link = this.links[i];
      var other = null;
      if (link.from_cuid === node.cuid) other = map[link.to_cuid];
      else if (link.to_cuid === node.cuid) other = map[link.from_cuid];
      if (!other) continue;

      var proj = this._project(other.x3d, other.y3d, other.z3d);
      var otherR = other.r * proj.scale * this.camera.zoom;
      ctx.strokeStyle = other.color;
      ctx.globalAlpha = 0.4;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(proj.x, proj.y, otherR + 3, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  };

  /* ---- Cleanup ---- */
  KnowledgeStarMap.prototype.destroy = function () {
    if (this._animFrame) cancelAnimationFrame(this._animFrame);
    this.canvas.removeEventListener("wheel", this._bound.onWheel);
    this.canvas.removeEventListener("mousedown", this._bound.onMouseDown);
    this.canvas.removeEventListener("mousemove", this._bound.onMouseMove);
    this.canvas.removeEventListener("mouseup", this._bound.onMouseUp);
    document.removeEventListener("mouseup", this._bound.onMouseUpGlobal);
    if (this._tooltip) { this._tooltip.remove(); this._tooltip = null; }
  };

  // Expose globally
  window.KnowledgeStarMap = KnowledgeStarMap;
  window.BrainTopology = KnowledgeStarMap;
})();
