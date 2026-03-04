/**
 * Spirit Realm (靈域) — MUSEON Dashboard v2.0 PixiJS Engine
 *
 * Top-down pixel-art RPG map with 7 explorable regions.
 * Eastern mystical × Cyberpunk hybrid visual style.
 *
 * Dependencies: pixi.js v7.x (loaded as global PIXI)
 */
(function () {
  "use strict";

  // ═══════════════════════════════════════════════════
  //  Constants
  // ═══════════════════════════════════════════════════

  var MAP_W = 960;
  var MAP_H = 640;

  // Region definitions — positions relative to 960×640 logical space
  var REGIONS = {
    home:      { id: "home",      name: "\u9748\u5DE2",     nameEn: "Home",     x: 0.50, y: 0.50, tab: "organism",  color: 0xC9A96E, emoji: "\uD83C\uDFE0", radius: 64 },
    memory:    { id: "memory",    name: "\u8A18\u61B6\u68EE\u6797", nameEn: "Memory",   x: 0.15, y: 0.47, tab: "memory",    color: 0x3B82F6, emoji: "\uD83C\uDF32", radius: 52 },
    star:      { id: "star",      name: "\u661F\u5BBF\u95A3",  nameEn: "Star",     x: 0.50, y: 0.13, tab: "agent",     color: 0x8B5CF6, emoji: "\u2601\uFE0F", radius: 52 },
    evolution: { id: "evolution", name: "\u6F14\u5316\u8056\u6BBF", nameEn: "Evolution", x: 0.78, y: 0.18, tab: "evolution", color: 0x10B981, emoji: "\uD83C\uDFD4\uFE0F", radius: 52 },
    forge:     { id: "forge",     name: "\u9444\u5668\u574A",  nameEn: "Forge",    x: 0.85, y: 0.52, tab: "tools",     color: 0xF59E0B, emoji: "\uD83D\uDD27", radius: 52 },
    health:    { id: "health",    name: "\u990A\u751F\u5802",  nameEn: "Health",   x: 0.50, y: 0.85, tab: "doctor",    color: 0xEF4444, emoji: "\uD83D\uDCDC", radius: 52 },
    hub:       { id: "hub",       name: "\u6A1E\u7D10",     nameEn: "Hub",      x: 0.78, y: 0.82, tab: "settings",  color: 0x64748B, emoji: "\u2699\uFE0F", radius: 48 },
  };

  // Paths between regions (for visual connections)
  var PATHS = [
    ["home", "memory"],
    ["home", "star"],
    ["home", "evolution"],
    ["home", "forge"],
    ["home", "health"],
    ["home", "hub"],
    ["star", "evolution"],
    ["health", "hub"],
  ];

  // ═══════════════════════════════════════════════════
  //  Utility
  // ═══════════════════════════════════════════════════

  function hexToRGB(hex) {
    return {
      r: (hex >> 16) & 0xFF,
      g: (hex >> 8) & 0xFF,
      b: hex & 0xFF,
    };
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

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
    this._time = 0;
    this._onRegionClick = null;
    this._hoverRegion = null;
    this._activeRegion = null;
    this._destroyed = false;
    this._regionBadges = {};

    this._init();
  }

  // ── Initialization ──────────────────────────────

  SpiritRealm.prototype._init = function () {
    // Pixel art: nearest-neighbor scaling
    PIXI.BaseTexture.defaultOptions.scaleMode = PIXI.SCALE_MODES.NEAREST;

    this.app = new PIXI.Application({
      width: MAP_W,
      height: MAP_H,
      backgroundColor: 0x0A0F1C,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
      antialias: false,
      resizeTo: this.container,
    });

    this.container.appendChild(this.app.view);

    // Main world container
    this.mapContainer = new PIXI.Container();
    this.app.stage.addChild(this.mapContainer);

    // Build layers in order (back to front)
    this.layers.background = new PIXI.Container();
    this.layers.paths = new PIXI.Container();
    this.layers.regions = new PIXI.Container();
    this.layers.character = new PIXI.Container();
    this.layers.particles = new PIXI.Container();
    this.layers.labels = new PIXI.Container();

    this.mapContainer.addChild(this.layers.background);
    this.mapContainer.addChild(this.layers.paths);
    this.mapContainer.addChild(this.layers.regions);
    this.mapContainer.addChild(this.layers.character);
    this.mapContainer.addChild(this.layers.particles);
    this.mapContainer.addChild(this.layers.labels);

    this._buildBackground();
    this._buildPaths();
    this._buildRegions();
    this._buildCharacter();
    this._buildParticles();

    // Animation ticker
    var self = this;
    this.app.ticker.add(function (dt) {
      if (!self._destroyed) self._update(dt);
    });
  };

  // ── Background Layer ────────────────────────────

  SpiritRealm.prototype._buildBackground = function () {
    var g = new PIXI.Graphics();
    var w = this.app.screen.width;
    var h = this.app.screen.height;

    // Deep space gradient (radial dark center to slightly lighter edges)
    g.beginFill(0x0A0F1C);
    g.drawRect(0, 0, w, h);
    g.endFill();

    // Subtle grid pattern (ink-wash style)
    g.lineStyle(0.5, 0x141E30, 0.3);
    var gridSize = 48;
    for (var x = 0; x < w; x += gridSize) {
      g.moveTo(x, 0);
      g.lineTo(x, h);
    }
    for (var y = 0; y < h; y += gridSize) {
      g.moveTo(0, y);
      g.lineTo(w, y);
    }

    // Center glow (home region ambient light)
    var cx = w * 0.5, cy = h * 0.5;
    for (var r = 200; r > 0; r -= 20) {
      g.beginFill(0xC9A96E, 0.012);
      g.drawCircle(cx, cy, r);
      g.endFill();
    }

    this.layers.background.addChild(g);
  };

  // ── Path Layer ──────────────────────────────────

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

      // Neon dashed line
      var pathGfx = new PIXI.Graphics();
      this._drawDashedLine(pathGfx, x1, y1, x2, y2, 0x1A2840, 1.5, 0.4, 8, 6);
      this.layers.paths.addChild(pathGfx);

      // Glow overlay (thinner, brighter)
      var glowGfx = new PIXI.Graphics();
      this._drawDashedLine(glowGfx, x1, y1, x2, y2, 0x00FFF0, 0.5, 0.15, 8, 6);
      this.layers.paths.addChild(glowGfx);
    }
  };

  SpiritRealm.prototype._drawDashedLine = function (g, x1, y1, x2, y2, color, width, alpha, dashLen, gapLen) {
    g.lineStyle(width, color, alpha);
    var dx = x2 - x1, dy = y2 - y1;
    var dist = Math.sqrt(dx * dx + dy * dy);
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

  // ── Region Layer ────────────────────────────────

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
      var radius = def.radius;

      var regionContainer = new PIXI.Container();
      regionContainer.x = cx;
      regionContainer.y = cy;

      // 1. Outer glow ring (animated)
      var glowRing = new PIXI.Graphics();
      glowRing.beginFill(def.color, 0.08);
      glowRing.drawCircle(0, 0, radius + 16);
      glowRing.endFill();
      regionContainer.addChild(glowRing);

      // 2. Main region circle
      var mainCircle = new PIXI.Graphics();
      // Dark fill
      mainCircle.beginFill(0x141E30, 0.85);
      mainCircle.drawCircle(0, 0, radius);
      mainCircle.endFill();
      // Colored border
      mainCircle.lineStyle(2, def.color, 0.7);
      mainCircle.drawCircle(0, 0, radius);
      // Inner accent ring
      mainCircle.lineStyle(1, def.color, 0.25);
      mainCircle.drawCircle(0, 0, radius - 8);
      regionContainer.addChild(mainCircle);

      // 3. Emoji icon
      var emojiText = new PIXI.Text(def.emoji, {
        fontFamily: "system-ui, -apple-system, sans-serif",
        fontSize: rid === "home" ? 28 : 22,
        fill: 0xFFFFFF,
        align: "center",
      });
      emojiText.anchor.set(0.5, 0.5);
      emojiText.y = -6;
      regionContainer.addChild(emojiText);

      // 4. Region name label
      var nameText = new PIXI.Text(def.name, {
        fontFamily: "DM Sans, system-ui, sans-serif",
        fontSize: 11,
        fill: def.color,
        align: "center",
        fontWeight: "600",
      });
      nameText.anchor.set(0.5, 0);
      nameText.y = radius + 6;
      regionContainer.addChild(nameText);

      // 5. Badge placeholder (for status info)
      var badge = new PIXI.Text("", {
        fontFamily: "DM Sans, monospace",
        fontSize: 9,
        fill: 0x9A8B70,
        align: "center",
      });
      badge.anchor.set(0.5, 0);
      badge.y = radius + 22;
      badge.visible = false;
      regionContainer.addChild(badge);
      this._regionBadges[rid] = badge;

      // 6. Hit area + interaction
      regionContainer.eventMode = "static";
      regionContainer.cursor = "pointer";
      regionContainer.hitArea = new PIXI.Circle(0, 0, radius + 10);

      // Closure for event handlers
      (function (regionId, container, glow, main) {
        container.on("pointerdown", function () {
          self._handleRegionClick(regionId);
        });
        container.on("pointerover", function () {
          self._hoverRegion = regionId;
          main.tint = 0xFFFFFF;
          container.scale.set(1.06);
        });
        container.on("pointerout", function () {
          self._hoverRegion = null;
          main.tint = 0xFFFFFF;
          container.scale.set(1.0);
        });
      })(rid, regionContainer, glowRing, mainCircle);

      this.regionDisplays[rid] = {
        container: regionContainer,
        glow: glowRing,
        main: mainCircle,
        emoji: emojiText,
        nameText: nameText,
        def: def,
      };

      this.layers.regions.addChild(regionContainer);
    }
  };

  // ── Character Layer (霓裳 placeholder) ──────────

  SpiritRealm.prototype._buildCharacter = function () {
    var frames = [];

    for (var i = 0; i < 4; i++) {
      var g = new PIXI.Graphics();
      var breathOffset = Math.sin(i * Math.PI / 2) * 1.5;

      // Body — rounded spirit beast shape
      g.beginFill(0xC9A96E);
      g.drawRoundedRect(-12, -14 + breathOffset, 24, 28 - breathOffset, 8);
      g.endFill();

      // Inner glow
      g.beginFill(0xDFC08A, 0.4);
      g.drawRoundedRect(-8, -10 + breathOffset, 16, 20 - breathOffset, 5);
      g.endFill();

      // Eyes
      g.beginFill(0x3B82F6);
      g.drawCircle(-4, -4 + breathOffset * 0.5, 2.5);
      g.drawCircle(4, -4 + breathOffset * 0.5, 2.5);
      g.endFill();

      // Eye sparkle
      g.beginFill(0xFFFFFF);
      g.drawCircle(-3, -5 + breathOffset * 0.5, 0.8);
      g.drawCircle(5, -5 + breathOffset * 0.5, 0.8);
      g.endFill();

      // Mouth (tiny smile)
      g.lineStyle(1, 0x9A7D4E, 0.6);
      g.arc(0, 0 + breathOffset * 0.3, 3, 0.2, Math.PI - 0.2);

      // Ears/horns (mystical style)
      g.lineStyle(0);
      g.beginFill(0xC9A96E);
      g.moveTo(-10, -12 + breathOffset);
      g.lineTo(-14, -22 + breathOffset);
      g.lineTo(-6, -14 + breathOffset);
      g.closePath();
      g.endFill();

      g.beginFill(0xC9A96E);
      g.moveTo(10, -12 + breathOffset);
      g.lineTo(14, -22 + breathOffset);
      g.lineTo(6, -14 + breathOffset);
      g.closePath();
      g.endFill();

      // Ear tips glow (cyber accent)
      g.beginFill(0x00FFF0, 0.7);
      g.drawCircle(-14, -22 + breathOffset, 1.5);
      g.drawCircle(14, -22 + breathOffset, 1.5);
      g.endFill();

      var texture = this.app.renderer.generateTexture(g, {
        resolution: 2,
        region: new PIXI.Rectangle(-20, -28, 40, 40),
      });
      frames.push(texture);
      g.destroy();
    }

    this.character = new PIXI.AnimatedSprite(frames);
    this.character.animationSpeed = 0.06;
    this.character.anchor.set(0.5, 0.5);
    this.character.scale.set(1.8);
    this.character.play();

    // Position at home
    var w = this.app.screen.width;
    var h = this.app.screen.height;
    this.character.x = REGIONS.home.x * w;
    this.character.y = REGIONS.home.y * h - 8; // Slightly above center

    // Subtle float animation is handled in _update()
    this._charBaseY = this.character.y;

    this.layers.character.addChild(this.character);

    // Shadow under character
    var shadow = new PIXI.Graphics();
    shadow.beginFill(0x000000, 0.2);
    shadow.drawEllipse(0, 0, 14, 5);
    shadow.endFill();
    shadow.x = this.character.x;
    shadow.y = this.character.y + 22;
    this._charShadow = shadow;
    this.layers.character.addChild(shadow);
    // Move shadow behind character
    this.layers.character.setChildIndex(shadow, 0);
  };

  // ── Particle Layer ──────────────────────────────

  SpiritRealm.prototype._buildParticles = function () {
    var w = this.app.screen.width;
    var h = this.app.screen.height;

    for (var i = 0; i < 20; i++) {
      var p = new PIXI.Graphics();
      var size = 1 + Math.random() * 2;
      var color = [0x00FFF0, 0xC9A96E, 0x8B5CF6, 0x3B82F6][Math.floor(Math.random() * 4)];
      p.beginFill(color, 0.4 + Math.random() * 0.3);
      p.drawCircle(0, 0, size);
      p.endFill();

      // Glow halo
      p.beginFill(color, 0.1);
      p.drawCircle(0, 0, size * 3);
      p.endFill();

      p.x = Math.random() * w;
      p.y = Math.random() * h;

      this.particles.push({
        gfx: p,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.2 - 0.1,
        baseAlpha: p.alpha,
        phase: Math.random() * Math.PI * 2,
      });

      this.layers.particles.addChild(p);
    }
  };

  // ── Animation Update Loop ──────────────────────

  SpiritRealm.prototype._update = function (dt) {
    this._time += 0.016 * dt;
    var w = this.app.screen.width;
    var h = this.app.screen.height;

    // 1. Particle movement
    for (var i = 0; i < this.particles.length; i++) {
      var p = this.particles[i];
      p.gfx.x += p.vx * dt;
      p.gfx.y += p.vy * dt;
      p.gfx.alpha = p.baseAlpha * (0.5 + 0.5 * Math.sin(this._time * 2 + p.phase));

      // Wrap around
      if (p.gfx.x < -10) p.gfx.x = w + 10;
      if (p.gfx.x > w + 10) p.gfx.x = -10;
      if (p.gfx.y < -10) p.gfx.y = h + 10;
      if (p.gfx.y > h + 10) p.gfx.y = -10;
    }

    // 2. Region glow pulsing
    var regionIds = Object.keys(this.regionDisplays);
    for (var j = 0; j < regionIds.length; j++) {
      var rd = this.regionDisplays[regionIds[j]];
      var isActive = regionIds[j] === this._activeRegion;
      var isHover = regionIds[j] === this._hoverRegion;
      var isHome = regionIds[j] === "home";

      var baseAlpha = isHome ? 0.12 : 0.06;
      var targetAlpha = isActive ? 0.25 : (isHover ? 0.18 : baseAlpha);
      var pulse = Math.sin(this._time * 1.5 + j * 0.8) * 0.04;

      rd.glow.alpha = targetAlpha + pulse;

      // Scale pulse for active region
      if (isActive) {
        var s = 1.0 + Math.sin(this._time * 2) * 0.015;
        rd.container.scale.set(s);
      } else if (!isHover) {
        // Smooth return to normal
        rd.container.scale.set(lerp(rd.container.scale.x, 1.0, 0.1));
      }
    }

    // 3. Character float animation
    if (this.character) {
      var floatY = Math.sin(this._time * 1.2) * 3;
      this.character.y = this._charBaseY + floatY;
      if (this._charShadow) {
        this._charShadow.y = this._charBaseY + 22;
        this._charShadow.scale.x = 1.0 - Math.abs(floatY) * 0.02;
      }
    }
  };

  // ── Event Handlers ─────────────────────────────

  SpiritRealm.prototype._handleRegionClick = function (regionId) {
    this._activeRegion = regionId;

    // Flash feedback
    var rd = this.regionDisplays[regionId];
    if (rd) {
      rd.glow.alpha = 0.8;
    }

    // Callback to host app
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
    var targetY = def.y * h - 8;

    // Smooth movement via ticker
    var self = this;
    var startX = this.character.x;
    var startY = this._charBaseY;
    var progress = 0;
    var duration = 30; // frames

    var moveTicker = function (dt) {
      progress += dt;
      var t = Math.min(1, progress / duration);
      // Ease-out cubic
      var ease = 1 - Math.pow(1 - t, 3);
      self.character.x = lerp(startX, targetX, ease);
      self._charBaseY = lerp(startY, targetY, ease);
      if (self._charShadow) {
        self._charShadow.x = self.character.x;
      }
      if (t >= 1) {
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
    this._regionBadges = {};
  };

  // ── Expose ─────────────────────────────────────

  window.SpiritRealm = SpiritRealm;

})();
