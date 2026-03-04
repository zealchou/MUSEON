/**
 * Spirit Realm (靈域) — MUSEON Dashboard v2.0 PixiJS Engine
 *
 * Full-screen top-down pixel-art RPG map with 7 explorable regions.
 * Eastern mystical × Cyberpunk hybrid visual style.
 * This is the ONLY interface — no classic tabs mode.
 *
 * Dependencies: pixi.js v7.x (loaded as global PIXI)
 */
(function () {
  "use strict";

  // ═══════════════════════════════════════════════════
  //  Constants & Config
  // ═══════════════════════════════════════════════════

  var MAP_W = 960;
  var MAP_H = 640;

  // Color palette — Eastern mystical × Cyberpunk
  var PALETTE = {
    bgDeep:     0x060B18,
    bgMid:      0x0A1025,
    bgLight:    0x101830,
    gold:       0xC9A96E,
    goldLight:  0xDFC08A,
    goldDark:   0x9A7D4E,
    cyan:       0x00FFF0,
    cyanDim:    0x00887A,
    purple:     0x8B5CF6,
    blue:       0x3B82F6,
    green:      0x10B981,
    red:        0xEF4444,
    amber:      0xF59E0B,
    slate:      0x64748B,
    cream:      0xF3EDE0,
  };

  // Region definitions — positions relative to screen, with visual theme
  var REGIONS = {
    home: {
      id: "home", name: "靈巢", nameEn: "Nexus",
      x: 0.50, y: 0.48, tab: "organism",
      color: PALETTE.gold, accent: PALETTE.cyan,
      icon: "home", radius: 56, glow: 0.18,
    },
    memory: {
      id: "memory", name: "記憶森林", nameEn: "Memory Grove",
      x: 0.14, y: 0.45, tab: "memory",
      color: PALETTE.blue, accent: 0x60A5FA,
      icon: "tree", radius: 44, glow: 0.12,
    },
    star: {
      id: "star", name: "星宿閣", nameEn: "Star Pavilion",
      x: 0.50, y: 0.12, tab: "agent",
      color: PALETTE.purple, accent: 0xA78BFA,
      icon: "star", radius: 44, glow: 0.12,
    },
    evolution: {
      id: "evolution", name: "演化聖殿", nameEn: "Evolution Shrine",
      x: 0.82, y: 0.20, tab: "evolution",
      color: PALETTE.green, accent: 0x34D399,
      icon: "temple", radius: 44, glow: 0.12,
    },
    forge: {
      id: "forge", name: "鑄器坊", nameEn: "The Forge",
      x: 0.86, y: 0.55, tab: "tools",
      color: PALETTE.amber, accent: 0xFBBF24,
      icon: "forge", radius: 44, glow: 0.12,
    },
    health: {
      id: "health", name: "養生堂", nameEn: "Vitality Hall",
      x: 0.35, y: 0.85, tab: "doctor",
      color: PALETTE.red, accent: 0xF87171,
      icon: "health", radius: 42, glow: 0.10,
    },
    hub: {
      id: "hub", name: "樞紐", nameEn: "Hub",
      x: 0.72, y: 0.82, tab: "settings",
      color: PALETTE.slate, accent: 0x94A3B8,
      icon: "gear", radius: 40, glow: 0.10,
    },
  };

  // Paths between regions (for visual energy connections)
  var PATHS = [
    ["home", "memory"],
    ["home", "star"],
    ["home", "evolution"],
    ["home", "forge"],
    ["home", "health"],
    ["home", "hub"],
    ["star", "evolution"],
    ["health", "hub"],
    ["memory", "health"],
    ["forge", "hub"],
  ];

  // ═══════════════════════════════════════════════════
  //  Utility
  // ═══════════════════════════════════════════════════

  function lerp(a, b, t) { return a + (b - a) * t; }

  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }

  // ═══════════════════════════════════════════════════
  //  SpiritRealm Class
  // ═══════════════════════════════════════════════════

  function SpiritRealm(containerElement, options) {
    if (!containerElement) throw new Error("[SpiritRealm] containerElement required");
    if (typeof PIXI === "undefined") throw new Error("[SpiritRealm] PIXI not loaded");

    this.container = containerElement;
    this.options = options || {};
    this.app = null;
    this.mapContainer = null;
    this.layers = {};
    this.regionDisplays = {};
    this.character = null;
    this.particles = [];
    this.stars = [];
    this.pathParticles = [];
    this.lanterns = [];
    this._time = 0;
    this._onRegionClick = null;
    this._hoverRegion = null;
    this._activeRegion = null;
    this._destroyed = false;
    this._regionBadges = {};
    this._charBaseY = 0;
    this._charShadow = null;

    this._init();
  }

  // ── Initialization ──────────────────────────────

  SpiritRealm.prototype._init = function () {
    PIXI.BaseTexture.defaultOptions.scaleMode = PIXI.SCALE_MODES.NEAREST;

    this.app = new PIXI.Application({
      width: MAP_W,
      height: MAP_H,
      backgroundColor: PALETTE.bgDeep,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
      antialias: false,
      resizeTo: this.container,
    });

    this.container.appendChild(this.app.view);

    // Main world container
    this.mapContainer = new PIXI.Container();
    this.app.stage.addChild(this.mapContainer);

    // Build layers (back to front)
    var layerNames = ["background", "nebula", "stars", "paths", "pathFx", "regions", "character", "particles", "lanterns", "labels", "vignette"];
    for (var i = 0; i < layerNames.length; i++) {
      this.layers[layerNames[i]] = new PIXI.Container();
      this.mapContainer.addChild(this.layers[layerNames[i]]);
    }

    this._buildBackground();
    this._buildNebula();
    this._buildStarField();
    this._buildPaths();
    this._buildRegions();
    this._buildCharacter();
    this._buildParticles();
    this._buildLanterns();
    this._buildVignette();

    // Animation ticker
    var self = this;
    this.app.ticker.add(function (dt) {
      if (!self._destroyed) self._update(dt);
    });
  };

  // ── Background — Multi-layer gradient ─────────

  SpiritRealm.prototype._buildBackground = function () {
    var g = new PIXI.Graphics();
    var w = this.app.screen.width;
    var h = this.app.screen.height;

    // Base fill
    g.beginFill(PALETTE.bgDeep);
    g.drawRect(0, 0, w, h);
    g.endFill();

    // Radial center glow (warm golden, subtle)
    var cx = w * 0.5, cy = h * 0.48;
    for (var r = 300; r > 0; r -= 8) {
      var alpha = 0.015 * (1 - r / 300);
      g.beginFill(PALETTE.gold, alpha);
      g.drawCircle(cx, cy, r);
      g.endFill();
    }

    // Subtle cyan accent glow (top-right)
    for (var r2 = 200; r2 > 0; r2 -= 10) {
      g.beginFill(PALETTE.cyan, 0.006 * (1 - r2 / 200));
      g.drawCircle(w * 0.82, h * 0.15, r2);
      g.endFill();
    }

    // Purple accent glow (bottom-left)
    for (var r3 = 180; r3 > 0; r3 -= 10) {
      g.beginFill(PALETTE.purple, 0.005 * (1 - r3 / 180));
      g.drawCircle(w * 0.15, h * 0.8, r3);
      g.endFill();
    }

    this.layers.background.addChild(g);
  };

  // ── Nebula clouds ──────────────────────────────

  SpiritRealm.prototype._buildNebula = function () {
    var w = this.app.screen.width;
    var h = this.app.screen.height;

    var cloudConfigs = [
      { x: w * 0.2,  y: h * 0.3,  rx: 120, ry: 50,  color: PALETTE.blue,   alpha: 0.03 },
      { x: w * 0.7,  y: h * 0.2,  rx: 100, ry: 40,  color: PALETTE.purple, alpha: 0.025 },
      { x: w * 0.5,  y: h * 0.7,  rx: 140, ry: 45,  color: PALETTE.gold,   alpha: 0.02 },
      { x: w * 0.85, y: h * 0.6,  rx: 90,  ry: 35,  color: PALETTE.cyan,   alpha: 0.02 },
      { x: w * 0.3,  y: h * 0.6,  rx: 110, ry: 40,  color: PALETTE.green,  alpha: 0.018 },
    ];

    for (var i = 0; i < cloudConfigs.length; i++) {
      var cfg = cloudConfigs[i];
      var cloud = new PIXI.Graphics();
      for (var j = 3; j >= 0; j--) {
        var scale = 1 + j * 0.3;
        cloud.beginFill(cfg.color, cfg.alpha / (j + 1));
        cloud.drawEllipse(0, 0, cfg.rx * scale, cfg.ry * scale);
        cloud.endFill();
      }
      cloud.x = cfg.x;
      cloud.y = cfg.y;
      cloud._driftSpeed = 0.05 + Math.random() * 0.08;
      cloud._driftPhase = Math.random() * Math.PI * 2;
      cloud._baseX = cfg.x;
      this.layers.nebula.addChild(cloud);
    }
  };

  // ── Star field — twinkling background stars ───

  SpiritRealm.prototype._buildStarField = function () {
    var w = this.app.screen.width;
    var h = this.app.screen.height;

    for (var i = 0; i < 120; i++) {
      var g = new PIXI.Graphics();
      var size = 0.5 + Math.random() * 1.5;
      var brightness = 0.2 + Math.random() * 0.5;
      var color = Math.random() > 0.8
        ? (Math.random() > 0.5 ? PALETTE.cyan : PALETTE.gold)
        : 0xFFFFFF;

      g.beginFill(color, brightness);
      g.drawCircle(0, 0, size);
      g.endFill();

      if (size > 1) {
        g.beginFill(color, brightness * 0.15);
        g.drawCircle(0, 0, size * 2.5);
        g.endFill();
      }

      g.x = Math.random() * w;
      g.y = Math.random() * h;

      this.stars.push({
        gfx: g,
        phase: Math.random() * Math.PI * 2,
        speed: 0.5 + Math.random() * 2,
        baseAlpha: brightness,
      });

      this.layers.stars.addChild(g);
    }
  };

  // ── Path Layer — Energy streams ───────────────

  SpiritRealm.prototype._buildPaths = function () {
    var w = this.app.screen.width;
    var h = this.app.screen.height;

    for (var i = 0; i < PATHS.length; i++) {
      var pathDef = PATHS[i];
      var from = REGIONS[pathDef[0]];
      var to = REGIONS[pathDef[1]];
      if (!from || !to) continue;

      var x1 = from.x * w, y1 = from.y * h;
      var x2 = to.x * w, y2 = to.y * h;

      // Soft glow line (wide, dim)
      var glowLine = new PIXI.Graphics();
      glowLine.lineStyle(4, 0x1A2840, 0.2);
      glowLine.moveTo(x1, y1);
      glowLine.lineTo(x2, y2);
      this.layers.paths.addChild(glowLine);

      // Thin bright line
      var thinLine = new PIXI.Graphics();
      thinLine.lineStyle(1, PALETTE.cyanDim, 0.15);
      thinLine.moveTo(x1, y1);
      thinLine.lineTo(x2, y2);
      this.layers.paths.addChild(thinLine);

      // Dashed overlay
      var dashGfx = new PIXI.Graphics();
      this._drawDashedLine(dashGfx, x1, y1, x2, y2, PALETTE.cyan, 0.8, 0.08, 6, 10);
      this.layers.paths.addChild(dashGfx);

      // Flowing energy particles along each path
      var dist = Math.sqrt((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1));
      var numPathP = Math.floor(dist / 80) + 1;
      for (var j = 0; j < numPathP; j++) {
        var pp = new PIXI.Graphics();
        pp.beginFill(PALETTE.cyan, 0.6);
        pp.drawCircle(0, 0, 1.2);
        pp.endFill();
        pp.beginFill(PALETTE.cyan, 0.12);
        pp.drawCircle(0, 0, 4);
        pp.endFill();

        this.pathParticles.push({
          gfx: pp,
          x1: x1, y1: y1,
          x2: x2, y2: y2,
          t: j / numPathP,
          speed: 0.002 + Math.random() * 0.003,
        });
        this.layers.pathFx.addChild(pp);
      }
    }
  };

  SpiritRealm.prototype._drawDashedLine = function (g, x1, y1, x2, y2, color, width, alpha, dashLen, gapLen) {
    g.lineStyle(width, color, alpha);
    var dx = x2 - x1, dy = y2 - y1;
    var dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 1) return;
    var nx = dx / dist, ny = dy / dist;
    var drawn = 0;
    var drawing = true;
    while (drawn < dist) {
      var segLen = drawing ? dashLen : gapLen;
      if (drawn + segLen > dist) segLen = dist - drawn;
      if (drawing) {
        g.moveTo(x1 + nx * drawn, y1 + ny * drawn);
        g.lineTo(x1 + nx * (drawn + segLen), y1 + ny * (drawn + segLen));
      }
      drawn += segLen;
      drawing = !drawing;
    }
  };

  // ── Region Layer — Hexagonal platforms ─────────

  SpiritRealm.prototype._buildRegions = function () {
    var w = this.app.screen.width;
    var h = this.app.screen.height;
    var self = this;

    var regionIds = Object.keys(REGIONS);
    for (var i = 0; i < regionIds.length; i++) {
      var rid = regionIds[i];
      var def = REGIONS[rid];
      var cx = def.x * w;
      var cy = def.y * h;
      var R = def.radius;

      var regionContainer = new PIXI.Container();
      regionContainer.x = cx;
      regionContainer.y = cy;

      // 1. Outer aura (soft, animated)
      var aura = new PIXI.Graphics();
      for (var a = 3; a >= 0; a--) {
        aura.beginFill(def.color, 0.02 * (4 - a));
        aura.drawCircle(0, 0, R + 20 + a * 12);
        aura.endFill();
      }
      regionContainer.addChild(aura);

      // 2. Platform base (hexagonal shape)
      var platform = new PIXI.Graphics();
      // Shadow
      platform.beginFill(0x000000, 0.3);
      this._drawHex(platform, 3, 5, R + 2);
      platform.endFill();
      // Base fill
      platform.beginFill(PALETTE.bgMid, 0.92);
      this._drawHex(platform, 0, 0, R);
      platform.endFill();
      // Inner gradient fill
      platform.beginFill(def.color, 0.06);
      this._drawHex(platform, 0, 0, R - 4);
      platform.endFill();
      // Border
      platform.lineStyle(2, def.color, 0.6);
      this._drawHex(platform, 0, 0, R);
      // Inner ring
      platform.lineStyle(1, def.color, 0.15);
      this._drawHex(platform, 0, 0, R - 10);
      regionContainer.addChild(platform);

      // 3. Region icon (drawn with Graphics)
      var iconContainer = new PIXI.Container();
      this._drawRegionIcon(iconContainer, def.icon, def.color, def.accent);
      iconContainer.y = -4;
      regionContainer.addChild(iconContainer);

      // 4. Name label — below platform
      var nameText = new PIXI.Text(def.name, {
        fontFamily: "'PingFang SC', 'Noto Sans SC', 'Microsoft YaHei', system-ui, sans-serif",
        fontSize: 11,
        fill: def.color,
        align: "center",
        fontWeight: "600",
        letterSpacing: 1,
        dropShadow: true,
        dropShadowColor: 0x000000,
        dropShadowDistance: 1,
        dropShadowAngle: Math.PI / 2,
        dropShadowBlur: 2,
        dropShadowAlpha: 0.5,
      });
      nameText.anchor.set(0.5, 0);
      nameText.y = R + 8;
      regionContainer.addChild(nameText);

      // 5. English sub-label
      var enText = new PIXI.Text(def.nameEn, {
        fontFamily: "DM Sans, system-ui, sans-serif",
        fontSize: 8,
        fill: 0x4A5568,
        align: "center",
        fontWeight: "400",
      });
      enText.anchor.set(0.5, 0);
      enText.y = R + 22;
      regionContainer.addChild(enText);

      // 6. Status badge
      var badge = new PIXI.Text("", {
        fontFamily: "DM Sans, monospace",
        fontSize: 9,
        fill: PALETTE.cream,
        align: "center",
      });
      badge.anchor.set(0.5, 0);
      badge.y = R + 34;
      badge.visible = false;
      regionContainer.addChild(badge);
      this._regionBadges[rid] = badge;

      // 7. Corner sparkles
      var sparkles = new PIXI.Graphics();
      for (var s = 0; s < 4; s++) {
        var angle = (s / 4) * Math.PI * 2 + Math.PI / 4;
        var sx = Math.cos(angle) * (R + 6);
        var sy = Math.sin(angle) * (R + 6);
        sparkles.beginFill(def.accent, 0.5);
        sparkles.drawCircle(sx, sy, 1.2);
        sparkles.endFill();
      }
      regionContainer.addChild(sparkles);

      // 8. Hit area + interaction
      regionContainer.eventMode = "static";
      regionContainer.cursor = "pointer";
      regionContainer.hitArea = new PIXI.Circle(0, 0, R + 16);

      (function (regionId, container, auraGfx, platformGfx) {
        container.on("pointerdown", function () {
          self._handleRegionClick(regionId);
        });
        container.on("pointerover", function () {
          self._hoverRegion = regionId;
          container.scale.set(1.08);
        });
        container.on("pointerout", function () {
          self._hoverRegion = null;
        });
      })(rid, regionContainer, aura, platform);

      this.regionDisplays[rid] = {
        container: regionContainer,
        aura: aura,
        platform: platform,
        nameText: nameText,
        def: def,
      };

      this.layers.regions.addChild(regionContainer);
    }
  };

  // Draw a hexagon path
  SpiritRealm.prototype._drawHex = function (g, cx, cy, r) {
    var points = [];
    for (var i = 0; i < 6; i++) {
      var angle = (Math.PI / 3) * i - Math.PI / 6;
      points.push(cx + r * Math.cos(angle));
      points.push(cy + r * Math.sin(angle));
    }
    g.drawPolygon(points);
  };

  // Draw themed icon for each region
  SpiritRealm.prototype._drawRegionIcon = function (container, iconType, color, accent) {
    var g = new PIXI.Graphics();

    switch (iconType) {
      case "home":
        // Nexus orb with orbiting dots
        g.beginFill(accent, 0.8);
        g.drawCircle(0, 0, 10);
        g.endFill();
        g.beginFill(color, 0.6);
        g.drawCircle(0, 0, 6);
        g.endFill();
        g.beginFill(0xFFFFFF, 0.5);
        g.drawCircle(0, 0, 3);
        g.endFill();
        for (var i = 0; i < 3; i++) {
          var a = (i / 3) * Math.PI * 2;
          g.beginFill(accent, 0.6);
          g.drawCircle(Math.cos(a) * 16, Math.sin(a) * 16, 2);
          g.endFill();
        }
        break;

      case "tree":
        // Stylized tree
        g.beginFill(0x1B4332);
        g.drawRect(-2, 2, 4, 10);
        g.endFill();
        g.beginFill(color, 0.8);
        g.drawCircle(0, -4, 10);
        g.endFill();
        g.beginFill(accent, 0.4);
        g.drawCircle(-3, -6, 5);
        g.endFill();
        g.beginFill(0xFFFFFF, 0.2);
        g.drawCircle(2, -8, 3);
        g.endFill();
        break;

      case "star":
        // Constellation
        g.lineStyle(1.5, accent, 0.7);
        g.moveTo(0, -12); g.lineTo(4, -4); g.lineTo(12, -2);
        g.moveTo(0, -12); g.lineTo(-5, -3); g.lineTo(-10, 2);
        g.moveTo(4, -4); g.lineTo(2, 6);
        g.lineStyle(0);
        g.beginFill(color, 0.9);
        g.drawCircle(0, -12, 3);
        g.drawCircle(4, -4, 2);
        g.drawCircle(12, -2, 2);
        g.drawCircle(-5, -3, 2);
        g.drawCircle(-10, 2, 2);
        g.drawCircle(2, 6, 2);
        g.endFill();
        break;

      case "temple":
        // Mountain temple
        g.beginFill(color, 0.7);
        g.moveTo(0, -14);
        g.lineTo(12, 6);
        g.lineTo(-12, 6);
        g.closePath();
        g.endFill();
        g.beginFill(accent, 0.4);
        g.moveTo(0, -14);
        g.lineTo(6, 0);
        g.lineTo(-6, 0);
        g.closePath();
        g.endFill();
        g.beginFill(PALETTE.bgDeep, 0.8);
        g.drawRect(-3, 0, 6, 6);
        g.endFill();
        g.beginFill(accent, 0.8);
        g.drawCircle(0, -14, 2);
        g.endFill();
        break;

      case "forge":
        // Anvil with sparks
        g.beginFill(color, 0.8);
        g.drawRect(-10, 2, 20, 4);
        g.drawRect(-6, -2, 12, 4);
        g.endFill();
        g.beginFill(accent, 0.7);
        g.drawRect(-1, -14, 2, 12);
        g.endFill();
        g.beginFill(accent, 0.9);
        g.drawRect(-5, -16, 10, 4);
        g.endFill();
        g.beginFill(0xFFFFFF, 0.6);
        g.drawCircle(8, -6, 1);
        g.drawCircle(-7, -8, 1);
        g.drawCircle(5, -10, 0.8);
        g.endFill();
        break;

      case "health":
        // Medicine cross
        g.beginFill(color, 0.7);
        g.drawRoundedRect(-8, -10, 16, 20, 3);
        g.endFill();
        g.beginFill(accent, 0.8);
        g.drawRect(-2, -6, 4, 12);
        g.drawRect(-5, -1, 10, 4);
        g.endFill();
        g.beginFill(0xFFFFFF, 0.15);
        g.drawRoundedRect(-6, -8, 12, 16, 2);
        g.endFill();
        break;

      case "gear":
        // Gear mechanism
        g.lineStyle(2.5, color, 0.7);
        g.drawCircle(0, 0, 8);
        g.lineStyle(0);
        g.beginFill(PALETTE.bgDeep);
        g.drawCircle(0, 0, 4);
        g.endFill();
        g.beginFill(accent, 0.6);
        g.drawCircle(0, 0, 2);
        g.endFill();
        for (var t = 0; t < 6; t++) {
          var ta = (t / 6) * Math.PI * 2;
          g.beginFill(color, 0.6);
          g.drawRect(
            Math.cos(ta) * 8 - 1.5,
            Math.sin(ta) * 8 - 1.5,
            3, 3
          );
          g.endFill();
        }
        break;
    }

    container.addChild(g);
  };

  // ── Character Layer (霓裳) ────────────────────

  SpiritRealm.prototype._buildCharacter = function () {
    var frames = [];

    for (var i = 0; i < 6; i++) {
      var g = new PIXI.Graphics();
      var ft = i / 6;
      var breathOffset = Math.sin(ft * Math.PI * 2) * 2;
      var tailWag = Math.sin(ft * Math.PI * 2 + 0.5) * 3;

      // Aura glow
      g.beginFill(PALETTE.cyan, 0.08);
      g.drawCircle(0, 0 + breathOffset * 0.3, 20);
      g.endFill();

      // Body
      g.beginFill(PALETTE.gold);
      g.drawRoundedRect(-14, -16 + breathOffset, 28, 32 - breathOffset, 10);
      g.endFill();

      // Belly highlight
      g.beginFill(PALETTE.goldLight, 0.5);
      g.drawRoundedRect(-8, -4 + breathOffset, 16, 16, 6);
      g.endFill();

      // Pattern marks
      g.beginFill(PALETTE.goldDark, 0.4);
      g.drawRect(-10, -10 + breathOffset, 3, 8);
      g.drawRect(7, -10 + breathOffset, 3, 8);
      g.endFill();

      // Eyes
      g.beginFill(PALETTE.cyan, 0.9);
      g.drawCircle(-5, -6 + breathOffset * 0.5, 3.5);
      g.drawCircle(5, -6 + breathOffset * 0.5, 3.5);
      g.endFill();
      g.beginFill(0x000020);
      g.drawCircle(-5, -5.5 + breathOffset * 0.5, 1.8);
      g.drawCircle(5, -5.5 + breathOffset * 0.5, 1.8);
      g.endFill();
      g.beginFill(0xFFFFFF, 0.9);
      g.drawCircle(-4, -7 + breathOffset * 0.5, 1.2);
      g.drawCircle(6, -7 + breathOffset * 0.5, 1.2);
      g.endFill();

      // Nose
      g.beginFill(PALETTE.goldDark, 0.6);
      g.drawCircle(0, -2 + breathOffset * 0.3, 1.5);
      g.endFill();

      // Mouth
      g.lineStyle(1, PALETTE.goldDark, 0.5);
      g.arc(0, 1 + breathOffset * 0.3, 3.5, 0.3, Math.PI - 0.3);

      // Ears
      g.lineStyle(0);
      g.beginFill(PALETTE.gold);
      g.moveTo(-11, -14 + breathOffset);
      g.lineTo(-18, -28 + breathOffset);
      g.lineTo(-7, -16 + breathOffset);
      g.closePath();
      g.endFill();
      g.beginFill(PALETTE.gold);
      g.moveTo(11, -14 + breathOffset);
      g.lineTo(18, -28 + breathOffset);
      g.lineTo(7, -16 + breathOffset);
      g.closePath();
      g.endFill();

      // Ear inner
      g.beginFill(PALETTE.goldLight, 0.4);
      g.moveTo(-10, -15 + breathOffset);
      g.lineTo(-15, -24 + breathOffset);
      g.lineTo(-8, -16 + breathOffset);
      g.closePath();
      g.endFill();
      g.beginFill(PALETTE.goldLight, 0.4);
      g.moveTo(10, -15 + breathOffset);
      g.lineTo(15, -24 + breathOffset);
      g.lineTo(8, -16 + breathOffset);
      g.closePath();
      g.endFill();

      // Ear tip crystals
      g.beginFill(PALETTE.cyan, 0.9);
      g.drawCircle(-18, -28 + breathOffset, 2);
      g.drawCircle(18, -28 + breathOffset, 2);
      g.endFill();
      g.beginFill(PALETTE.cyan, 0.3);
      g.drawCircle(-18, -28 + breathOffset, 4);
      g.drawCircle(18, -28 + breathOffset, 4);
      g.endFill();

      // Tail
      g.beginFill(PALETTE.gold, 0.8);
      g.moveTo(10, 10 + breathOffset * 0.5);
      g.lineTo(18 + tailWag, 4 + breathOffset * 0.3);
      g.lineTo(22 + tailWag, 8 + breathOffset * 0.3);
      g.lineTo(12, 14 + breathOffset * 0.5);
      g.closePath();
      g.endFill();
      g.beginFill(PALETTE.cyan, 0.5);
      g.drawCircle(22 + tailWag, 8 + breathOffset * 0.3, 2);
      g.endFill();

      // Feet
      g.beginFill(PALETTE.goldDark);
      g.drawCircle(-7, 16, 3);
      g.drawCircle(7, 16, 3);
      g.endFill();

      var texture = this.app.renderer.generateTexture(g, {
        resolution: 2,
        region: new PIXI.Rectangle(-28, -36, 56, 60),
      });
      frames.push(texture);
      g.destroy();
    }

    this.character = new PIXI.AnimatedSprite(frames);
    this.character.animationSpeed = 0.08;
    this.character.anchor.set(0.5, 0.5);
    this.character.scale.set(1.6);
    this.character.play();

    var w = this.app.screen.width;
    var h = this.app.screen.height;
    this.character.x = REGIONS.home.x * w;
    this.character.y = REGIONS.home.y * h - 10;
    this._charBaseY = this.character.y;

    this.layers.character.addChild(this.character);

    // Shadow
    var shadow = new PIXI.Graphics();
    shadow.beginFill(0x000000, 0.25);
    shadow.drawEllipse(0, 0, 16, 6);
    shadow.endFill();
    shadow.x = this.character.x;
    shadow.y = this.character.y + 28;
    this._charShadow = shadow;
    this.layers.character.addChild(shadow);
    this.layers.character.setChildIndex(shadow, 0);
  };

  // ── Ambient particles ──────────────────────────

  SpiritRealm.prototype._buildParticles = function () {
    var w = this.app.screen.width;
    var h = this.app.screen.height;

    for (var i = 0; i < 35; i++) {
      var p = new PIXI.Graphics();
      var size = 0.5 + Math.random() * 2.5;
      var colorSet = [PALETTE.cyan, PALETTE.gold, PALETTE.purple, PALETTE.blue, PALETTE.green, 0xFFFFFF];
      var color = colorSet[Math.floor(Math.random() * colorSet.length)];
      var baseAlpha = 0.2 + Math.random() * 0.4;

      p.beginFill(color, baseAlpha);
      p.drawCircle(0, 0, size);
      p.endFill();
      p.beginFill(color, baseAlpha * 0.15);
      p.drawCircle(0, 0, size * 3);
      p.endFill();

      p.x = Math.random() * w;
      p.y = Math.random() * h;

      this.particles.push({
        gfx: p,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.3 - 0.05,
        baseAlpha: baseAlpha,
        phase: Math.random() * Math.PI * 2,
        pulseSpeed: 1 + Math.random() * 2,
      });

      this.layers.particles.addChild(p);
    }
  };

  // ── Floating lanterns (東方仙俠 feel) ──────────

  SpiritRealm.prototype._buildLanterns = function () {
    var w = this.app.screen.width;
    var h = this.app.screen.height;

    for (var i = 0; i < 6; i++) {
      var lantern = new PIXI.Graphics();
      var lColor = Math.random() > 0.5 ? PALETTE.gold : PALETTE.amber;

      lantern.beginFill(lColor, 0.35);
      lantern.drawRoundedRect(-4, -6, 8, 10, 2);
      lantern.endFill();
      lantern.beginFill(lColor, 0.6);
      lantern.drawRoundedRect(-2, -4, 4, 6, 1);
      lantern.endFill();
      lantern.lineStyle(0.5, lColor, 0.3);
      lantern.moveTo(0, -6);
      lantern.lineTo(0, -10);
      lantern.lineStyle(0);
      lantern.beginFill(lColor, 0.06);
      lantern.drawCircle(0, 0, 16);
      lantern.endFill();

      lantern.x = 80 + Math.random() * (w - 160);
      lantern.y = 40 + Math.random() * (h - 100);

      this.lanterns.push({
        gfx: lantern,
        baseX: lantern.x,
        baseY: lantern.y,
        phase: Math.random() * Math.PI * 2,
        driftSpeed: 0.3 + Math.random() * 0.5,
        amplitude: 8 + Math.random() * 12,
      });

      this.layers.lanterns.addChild(lantern);
    }
  };

  // ── Vignette overlay ───────────────────────────

  SpiritRealm.prototype._buildVignette = function () {
    var w = this.app.screen.width;
    var h = this.app.screen.height;
    var g = new PIXI.Graphics();

    // Top edge
    for (var i = 0; i < 6; i++) {
      g.beginFill(PALETTE.bgDeep, 0.12 * (6 - i));
      g.drawRect(0, 0, w, 8 * (6 - i));
      g.endFill();
    }
    // Bottom edge
    for (var j = 0; j < 6; j++) {
      g.beginFill(PALETTE.bgDeep, 0.12 * (6 - j));
      g.drawRect(0, h - 8 * (6 - j), w, 8 * (6 - j));
      g.endFill();
    }
    // Left edge
    for (var k = 0; k < 4; k++) {
      g.beginFill(PALETTE.bgDeep, 0.08 * (4 - k));
      g.drawRect(0, 0, 12 * (4 - k), h);
      g.endFill();
    }
    // Right edge
    for (var l = 0; l < 4; l++) {
      g.beginFill(PALETTE.bgDeep, 0.08 * (4 - l));
      g.drawRect(w - 12 * (4 - l), 0, 12 * (4 - l), h);
      g.endFill();
    }

    this.layers.vignette.addChild(g);
  };

  // ── Animation Update Loop ──────────────────────

  SpiritRealm.prototype._update = function (dt) {
    this._time += 0.016 * dt;
    var t = this._time;
    var w = this.app.screen.width;
    var h = this.app.screen.height;

    // 1. Star twinkle
    for (var si = 0; si < this.stars.length; si++) {
      var star = this.stars[si];
      star.gfx.alpha = star.baseAlpha * (0.4 + 0.6 * Math.abs(Math.sin(t * star.speed + star.phase)));
    }

    // 2. Nebula drift
    var nebulae = this.layers.nebula.children;
    for (var ni = 0; ni < nebulae.length; ni++) {
      var cloud = nebulae[ni];
      if (cloud._baseX !== undefined) {
        cloud.x = cloud._baseX + Math.sin(t * cloud._driftSpeed + cloud._driftPhase) * 15;
      }
    }

    // 3. Particle movement
    for (var pi = 0; pi < this.particles.length; pi++) {
      var p = this.particles[pi];
      p.gfx.x += p.vx * dt;
      p.gfx.y += p.vy * dt;
      p.gfx.alpha = p.baseAlpha * (0.3 + 0.7 * Math.abs(Math.sin(t * p.pulseSpeed + p.phase)));

      if (p.gfx.x < -20) p.gfx.x = w + 20;
      if (p.gfx.x > w + 20) p.gfx.x = -20;
      if (p.gfx.y < -20) p.gfx.y = h + 20;
      if (p.gfx.y > h + 20) p.gfx.y = -20;
    }

    // 4. Path particles (flowing energy)
    for (var ppi = 0; ppi < this.pathParticles.length; ppi++) {
      var pp = this.pathParticles[ppi];
      pp.t += pp.speed * dt;
      if (pp.t > 1) pp.t -= 1;
      pp.gfx.x = lerp(pp.x1, pp.x2, pp.t);
      pp.gfx.y = lerp(pp.y1, pp.y2, pp.t);
      pp.gfx.alpha = 0.3 + 0.4 * Math.sin(pp.t * Math.PI);
    }

    // 5. Region glow pulsing
    var regionIds = Object.keys(this.regionDisplays);
    for (var ri = 0; ri < regionIds.length; ri++) {
      var rd = this.regionDisplays[regionIds[ri]];
      var isActive = regionIds[ri] === this._activeRegion;
      var isHover = regionIds[ri] === this._hoverRegion;
      var isHome = regionIds[ri] === "home";

      var baseAlpha = isHome ? 0.15 : rd.def.glow;
      var targetAlpha = isActive ? 0.35 : (isHover ? 0.25 : baseAlpha);
      var pulse = Math.sin(t * 1.8 + ri * 0.9) * 0.04;
      rd.aura.alpha = targetAlpha + pulse;

      var targetScale = isActive ? (1.0 + Math.sin(t * 2.2) * 0.02) : (isHover ? 1.08 : 1.0);
      rd.container.scale.set(lerp(rd.container.scale.x, targetScale, 0.12));
    }

    // 6. Character float
    if (this.character) {
      var floatY = Math.sin(t * 1.0) * 4;
      this.character.y = this._charBaseY + floatY;
      if (this._charShadow) {
        this._charShadow.y = this._charBaseY + 28;
        this._charShadow.x = this.character.x;
        this._charShadow.scale.x = 1.0 - Math.abs(floatY) * 0.015;
        this._charShadow.alpha = 0.25 - Math.abs(floatY) * 0.01;
      }
    }

    // 7. Floating lanterns
    for (var li = 0; li < this.lanterns.length; li++) {
      var lan = this.lanterns[li];
      lan.gfx.x = lan.baseX + Math.sin(t * lan.driftSpeed + lan.phase) * lan.amplitude * 0.5;
      lan.gfx.y = lan.baseY + Math.sin(t * lan.driftSpeed * 0.7 + lan.phase + 1) * lan.amplitude;
      lan.gfx.alpha = 0.6 + 0.3 * Math.sin(t * 1.5 + lan.phase);
    }
  };

  // ── Event Handlers ─────────────────────────────

  SpiritRealm.prototype._handleRegionClick = function (regionId) {
    this._activeRegion = regionId;

    var rd = this.regionDisplays[regionId];
    if (rd) {
      rd.aura.alpha = 1.0;
    }

    if (this._onRegionClick) {
      this._onRegionClick(regionId, REGIONS[regionId]);
    }
  };

  // ── Public API ─────────────────────────────────

  SpiritRealm.prototype.onRegionClick = function (callback) {
    this._onRegionClick = callback;
  };

  SpiritRealm.prototype.setCharacterPosition = function (regionId) {
    var def = REGIONS[regionId];
    if (!def || !this.character) return;

    var w = this.app.screen.width;
    var h = this.app.screen.height;
    var targetX = def.x * w;
    var targetY = def.y * h - 10;

    var self = this;
    var startX = this.character.x;
    var startY = this._charBaseY;
    var progress = 0;
    var duration = 40;

    var moveTicker = function (dt) {
      progress += dt;
      var pct = Math.min(1, progress / duration);
      var ease = easeOutCubic(pct);
      self.character.x = lerp(startX, targetX, ease);
      self._charBaseY = lerp(startY, targetY, ease);
      if (self._charShadow) {
        self._charShadow.x = self.character.x;
      }
      if (pct >= 1) {
        self.app.ticker.remove(moveTicker);
      }
    };
    this.app.ticker.add(moveTicker);
  };

  SpiritRealm.prototype.highlightRegion = function (regionId) {
    this._activeRegion = regionId;
  };

  SpiritRealm.prototype.updateRegionStatus = function (regionId, data) {
    var badge = this._regionBadges[regionId];
    if (!badge) return;
    if (data && data.badge) {
      badge.text = data.badge;
      badge.visible = true;
    } else {
      badge.visible = false;
    }
  };

  SpiritRealm.prototype.destroy = function () {
    this._destroyed = true;
    if (this.app) {
      this.app.destroy(true, { children: true, texture: true, baseTexture: true });
      this.app = null;
    }
    this.mapContainer = null;
    this.layers = {};
    this.regionDisplays = {};
    this.character = null;
    this.particles = [];
    this.stars = [];
    this.pathParticles = [];
    this.lanterns = [];
    this._regionBadges = {};
  };

  // ── Expose ─────────────────────────────────────

  window.SpiritRealm = SpiritRealm;

})();
