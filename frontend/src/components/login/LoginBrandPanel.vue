<template>
  <section class="brand-panel">
    <div class="chart-background">
      <svg viewBox="0 0 800 600" class="chart-svg" aria-hidden="true">
        <defs>
          <!-- DOT GRID pattern (prototipo) -->
          <pattern id="dotGrid" width="14" height="14" patternUnits="userSpaceOnUse">
            <circle cx="1.2" cy="1.2" r="1.05" fill="rgba(255,255,255,0.14)" />
            <circle cx="8" cy="8" r="0.85" fill="rgba(255,255,255,0.08)" />
          </pattern>

          <!-- Grilla de líneas finas (tipo blueprint) -->
          <pattern id="fineGrid" width="56" height="56" patternUnits="userSpaceOnUse">
            <path d="M56 0H0V56" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="1" />
          </pattern>

          <!-- Área -->
          <linearGradient id="areaGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#86b6ff" stop-opacity="0.16" />
            <stop offset="100%" stop-color="#86b6ff" stop-opacity="0" />
          </linearGradient>

          <!-- Glow -->
          <filter id="softGlow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <!-- GRADIENTE “SHIMMER” (se mueve por la línea, no la corta) -->
          <linearGradient id="shimmerGradient" x1="-40%" y1="0%" x2="0%" y2="0%">
            <stop offset="0%" stop-color="#9bc4ff" stop-opacity="0" />
            <stop offset="35%" stop-color="#9bc4ff" stop-opacity="0.15" />
            <stop offset="55%" stop-color="#9bc4ff" stop-opacity="0.85" />
            <stop offset="75%" stop-color="#9bc4ff" stop-opacity="0.15" />
            <stop offset="100%" stop-color="#9bc4ff" stop-opacity="0" />

            <animate attributeName="x1" from="-40%" to="60%" dur="5.5s" repeatCount="indefinite" />
            <animate attributeName="x2" from="0%" to="100%" dur="5.5s" repeatCount="indefinite" />
          </linearGradient>
        </defs>

        <!-- dotted grid -->
        <rect x="0" y="0" width="800" height="600" fill="url(#dotGrid)" opacity="0.55" />
        <!-- fine grid -->
        <rect x="0" y="0" width="800" height="600" fill="url(#fineGrid)" opacity="0.35" />

        <!-- subtle horizontal guide lines -->
        <g class="h-guides">
          <line x1="0" y1="120" x2="800" y2="120" />
          <line x1="0" y1="200" x2="800" y2="200" />
          <line x1="0" y1="280" x2="800" y2="280" />
          <line x1="0" y1="360" x2="800" y2="360" />
          <line x1="0" y1="440" x2="800" y2="440" />
        </g>

        <!-- secondary lines (muy sutiles como prototipo) -->
        <path
          d="M0 520 C140 500, 240 475, 340 490 S520 440, 620 460 S760 420, 800 430"
          class="line-secondary"
        />
        <path
          d="M0 470 C120 445, 230 410, 320 430 S520 385, 620 405 S760 355, 800 365"
          class="line-secondary"
          opacity="0.22"
        />
        <path
          d="M0 545 C110 525, 220 510, 330 520 S520 500, 630 515 S740 495, 800 505"
          class="line-secondary"
          opacity="0.16"
        />
        <path
          d="M0 410 C140 380, 250 360, 350 372 S520 330, 620 350 S740 300, 800 315"
          class="line-secondary"
          opacity="0.14"
        />
        <path
          d="M0 360 C150 330, 260 305, 360 320 S520 285, 620 300 S740 255, 800 270"
          class="line-secondary"
          opacity="0.10"
        />

        <!-- main base -->
        <path
          d="M0 470 C120 440, 220 395, 320 415 S520 365, 620 385 S760 330, 800 345"
          class="line-base"
        />

        <!-- area under main line -->
        <path
          d="M0 470 C120 440, 220 395, 320 415 S520 365, 620 385 S760 330, 800 345 L800 600 L0 600 Z"
          class="area"
        />

        <!-- glow under main -->
        <path
          d="M0 470 C120 440, 220 395, 320 415 S520 365, 620 385 S760 330, 800 345"
          class="line-glow"
        />

        <!-- main line -->
        <path
          d="M0 470 C120 440, 220 395, 320 415 S520 365, 620 385 S760 330, 800 345"
          class="line-primary"
        />

        <!-- shimmer overlay (this is the “live” feel, sober) -->
        <path
          d="M0 470 C120 440, 220 395, 320 415 S520 365, 620 385 S760 330, 800 345"
          class="line-shimmer"
        />

        <!-- moving live point -->
        <circle r="4.5" class="live-dot">
          <animateMotion
            dur="6s"
            repeatCount="indefinite"
            keySplines="0.2 0.0 0.2 1"
            keyTimes="0;1"
            calcMode="spline"
          >
            <mpath href="#mainPath" />
          </animateMotion>
        </circle>

        <!-- path reference for animateMotion -->
        <path
          id="mainPath"
          d="M0 470 C120 440, 220 395, 320 415 S520 365, 620 385 S760 330, 800 345"
          fill="none"
          stroke="none"
        />
      </svg>
    </div>

    <div class="branding">
      <h1>DEMO SA</h1>
      <p class="subtitle">Sistema de Gestión Empresarial</p>
      <p class="claim">Centralizá tu negocio.</p>
    </div>
  </section>
</template>

<style scoped>
.brand-panel {
  position: relative;
  width: calc(1250px - 460px);
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;

  /* match prototipo vibe */
  background: linear-gradient(145deg, #071b37 0%, #0d2a57 45%, #1a4ea5 100%);
}

/* vignette / depth (como mockup) */
.brand-panel::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 60% 35%, rgba(255, 255, 255, 0.1), rgba(0, 0, 0, 0.38));
  pointer-events: none;
}

.chart-background {
  position: absolute;
  inset: 0;
  opacity: 0.4; /* sube un poco para que se note como en el prototipo */
}

.chart-svg {
  width: 100%;
  height: 100%;
}

.h-guides line {
  stroke: rgba(255, 255, 255, 0.08);
  stroke-width: 1;
}

.line-secondary {
  fill: none;
  stroke: rgba(180, 210, 255, 0.35);
  stroke-width: 2;
  opacity: 0.18;
}

.line-base {
  fill: none;
  stroke: rgba(150, 200, 255, 0.14);
  stroke-width: 2.2;
}

.area {
  fill: url(#areaGradient);
  opacity: 0.34;
}

.line-glow {
  fill: none;
  stroke: rgba(120, 180, 255, 1);
  stroke-width: 3.4;
  opacity: 0.16;
  filter: url(#softGlow);
}

.line-primary {
  fill: none;
  stroke: rgba(120, 180, 255, 0.55);
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
  opacity: 0.75;
}

/* shimmer overlay = “movimiento continuo” sin cortar la línea */
.line-shimmer {
  fill: none;
  stroke: url(#shimmerGradient);
  stroke-width: 2.6;
  stroke-linecap: round;
  stroke-linejoin: round;
  opacity: 0.95;
  filter: drop-shadow(0 0 6px rgba(130, 190, 255, 0.55));
}

.live-dot {
  fill: rgba(160, 210, 255, 0.95);
  filter: drop-shadow(0 0 8px rgba(140, 200, 255, 0.7));
  opacity: 0.9;
}

.branding {
  position: relative;
  z-index: 2;
  text-align: center;
  transform: translateY(-8px);
}

.branding h1 {
  font-size: 54px;
  letter-spacing: 2px;
  font-weight: 700;
  margin-bottom: 14px;
}

.subtitle {
  opacity: 0.82;
  font-weight: 500;
  margin-bottom: 14px;
}

.claim {
  font-weight: 700;
  font-size: 18px;
  opacity: 0.92;
}

.chart-background {
  opacity: 0.48;
}
.h-guides line {
  stroke: rgba(255, 255, 255, 0.1);
}
.line-secondary {
  stroke: rgba(190, 220, 255, 0.4);
}
</style>
