import { useState, useEffect, useRef, useCallback } from "react";
import * as THREE from "three";

const TAU = Math.PI * 2;

// Torus parameters
const R = 3.2; // major radius
const r = 1.3; // minor radius

function torusPoint(u, v) {
  const x = (R + r * Math.cos(v)) * Math.cos(u);
  const y = (R + r * Math.cos(v)) * Math.sin(u);
  const z = r * Math.sin(v);
  return new THREE.Vector3(x, y, z);
}

function torusNormal(u, v) {
  const nx = Math.cos(v) * Math.cos(u);
  const ny = Math.cos(v) * Math.sin(u);
  const nz = Math.sin(v);
  return new THREE.Vector3(nx, ny, nz).normalize();
}

// Tangent along major circle (u direction)
function torusTangentU(u, v) {
  const tx = -(R + r * Math.cos(v)) * Math.sin(u);
  const ty = (R + r * Math.cos(v)) * Math.cos(u);
  const tz = 0;
  return new THREE.Vector3(tx, ty, tz).normalize();
}

// Tangent along minor circle (v direction)
function torusTangentV(u, v) {
  const tx = -r * Math.sin(v) * Math.cos(u);
  const ty = -r * Math.sin(v) * Math.sin(u);
  const tz = r * Math.cos(v);
  return new THREE.Vector3(tx, ty, tz).normalize();
}

function createArrow(origin, direction, length, color, headLen = 0.18, headW = 0.08) {
  const dir = direction.clone().normalize();
  const arrow = new THREE.ArrowHelper(dir, origin, length, color, headLen, headW);
  return arrow;
}

export default function HodgeDiagram() {
  const mountRef = useRef(null);
  const sceneRef = useRef(null);
  const rendererRef = useRef(null);
  const cameraRef = useRef(null);
  const groupRef = useRef(null);
  const frameRef = useRef(null);
  const mouseRef = useRef({ down: false, x: 0, y: 0 });
  const rotRef = useRef({ x: 0.35, y: 0 });

  const [activeLayer, setActiveLayer] = useState("all");
  const [autoRotate, setAutoRotate] = useState(true);
  const layerGroupsRef = useRef({});

  const buildScene = useCallback(() => {
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0a14);

    const group = new THREE.Group();
    scene.add(group);
    groupRef.current = group;

    // Lighting
    const ambient = new THREE.AmbientLight(0x334466, 0.6);
    scene.add(ambient);
    const dirLight = new THREE.DirectionalLight(0xffeedd, 0.8);
    dirLight.position.set(5, 8, 6);
    scene.add(dirLight);
    const backLight = new THREE.DirectionalLight(0x4466aa, 0.3);
    backLight.position.set(-4, -3, -5);
    scene.add(backLight);

    // Torus mesh (semi-transparent)
    const torusGeo = new THREE.TorusGeometry(R, r, 48, 96);
    const torusMat = new THREE.MeshPhysicalMaterial({
      color: 0x1a1a2e,
      transparent: true,
      opacity: 0.25,
      roughness: 0.6,
      metalness: 0.1,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const torusMesh = new THREE.Mesh(torusGeo, torusMat);
    group.add(torusMesh);

    // Wireframe overlay
    const wireGeo = new THREE.TorusGeometry(R, r, 24, 48);
    const wireMat = new THREE.MeshBasicMaterial({
      color: 0x2a2a4e,
      wireframe: true,
      transparent: true,
      opacity: 0.12,
    });
    group.add(new THREE.Mesh(wireGeo, wireMat));

    // --- Layer groups ---
    const exactGroup = new THREE.Group();
    const coexactGroup = new THREE.Group();
    const harmonicGroup = new THREE.Group();
    group.add(exactGroup);
    group.add(coexactGroup);
    group.add(harmonicGroup);
    layerGroupsRef.current = { exact: exactGroup, coexact: coexactGroup, harmonic: harmonicGroup };

    // === 1. EXACT COMPONENT (blue gradient arrows) ===
    // Flow from "high pressure" to "low pressure" along v direction
    const blueColor = 0x3b82f6;
    const highPressU = Math.PI * 0.25;
    const lowPressU = Math.PI * 1.25;

    for (let i = 0; i < 14; i++) {
      const t = i / 13;
      const u = highPressU + t * (lowPressU - highPressU);
      for (let j = 0; j < 6; j++) {
        const v = (j / 6) * TAU;
        const pt = torusPoint(u, v);
        const normal = torusNormal(u, v);
        const tangent = torusTangentU(u, v);
        const offset = normal.clone().multiplyScalar(0.08);
        const origin = pt.clone().add(offset);
        const len = 0.35 + 0.15 * Math.sin(t * Math.PI);
        const arrow = createArrow(origin, tangent, len, blueColor, 0.14, 0.06);
        exactGroup.add(arrow);
      }
    }

    // High/Low pressure markers
    const markerGeo = new THREE.SphereGeometry(0.15, 16, 16);
    const highMat = new THREE.MeshBasicMaterial({ color: 0x60a5fa });
    const lowMat = new THREE.MeshBasicMaterial({ color: 0x1e3a5f });
    const highPos = torusPoint(highPressU, 0);
    const lowPos = torusPoint(lowPressU, 0);
    const highMarker = new THREE.Mesh(markerGeo, highMat);
    highMarker.position.copy(highPos.clone().add(torusNormal(highPressU, 0).multiplyScalar(0.3)));
    const lowMarker = new THREE.Mesh(markerGeo, lowMat);
    lowMarker.position.copy(lowPos.clone().add(torusNormal(lowPressU, 0).multiplyScalar(0.3)));
    exactGroup.add(highMarker);
    exactGroup.add(lowMarker);

    // === 2. CO-EXACT COMPONENT (red vortices) ===
    const redColor = 0xef4444;
    const vortexCenters = [
      { u: 0, v: 0 },
      { u: Math.PI * 0.5, v: Math.PI },
      { u: Math.PI, v: Math.PI * 0.5 },
      { u: Math.PI * 1.5, v: Math.PI * 1.5 },
      { u: Math.PI * 0.75, v: Math.PI * 0.3 },
      { u: Math.PI * 1.75, v: Math.PI * 1.2 },
    ];

    vortexCenters.forEach(({ u: cu, v: cv }) => {
      const center = torusPoint(cu, cv);
      const norm = torusNormal(cu, cv);
      const tanU = torusTangentU(cu, cv);
      const tanV = torusTangentV(cu, cv);

      for (let k = 0; k < 8; k++) {
        const angle = (k / 8) * TAU;
        const rad = 0.28;
        const offU = Math.cos(angle) * rad;
        const offV = Math.sin(angle) * rad;

        const ptU = cu + offU * 0.08;
        const ptV = cv + offV * 0.15;
        const pt = torusPoint(ptU, ptV);
        const ptNorm = torusNormal(ptU, ptV);
        const origin = pt.clone().add(ptNorm.clone().multiplyScalar(0.1));

        // Tangent direction perpendicular to radial (spinning)
        const spinAngle = angle + Math.PI * 0.5;
        const dir = tanU.clone().multiplyScalar(Math.cos(spinAngle) * 0.6)
          .add(tanV.clone().multiplyScalar(Math.sin(spinAngle) * 0.6))
          .normalize();

        const arrow = createArrow(origin, dir, 0.25, redColor, 0.1, 0.05);
        coexactGroup.add(arrow);
      }

      // Vortex center marker
      const vGeo = new THREE.RingGeometry(0.08, 0.12, 16);
      const vMat = new THREE.MeshBasicMaterial({ color: redColor, side: THREE.DoubleSide, transparent: true, opacity: 0.7 });
      const vMesh = new THREE.Mesh(vGeo, vMat);
      vMesh.position.copy(center.clone().add(norm.clone().multiplyScalar(0.12)));
      vMesh.lookAt(center.clone().add(norm));
      coexactGroup.add(vMesh);
    });

    // === 3. HARMONIC COMPONENT (green flow around the hole) ===
    const greenColor = 0x22c55e;

    // Loop 1: around the central hole (major circle)
    for (let i = 0; i < 28; i++) {
      const u = (i / 28) * TAU;
      const v = Math.PI * 0.5; // ride on outer edge, top
      const pt = torusPoint(u, v);
      const norm = torusNormal(u, v);
      const tangent = torusTangentU(u, v);
      const origin = pt.clone().add(norm.clone().multiplyScalar(0.15));
      const arrow = createArrow(origin, tangent, 0.45, greenColor, 0.16, 0.07);
      harmonicGroup.add(arrow);
    }

    // Loop 2: through the hole (minor circle) at one position
    for (let j = 0; j < 16; j++) {
      const v = (j / 16) * TAU;
      const u = 0; // fixed position on major circle
      const pt = torusPoint(u, v);
      const norm = torusNormal(u, v);
      const tangent = torusTangentV(u, v);
      const origin = pt.clone().add(norm.clone().multiplyScalar(0.15));
      const arrow = createArrow(origin, tangent, 0.35, 0x16a34a, 0.13, 0.06);
      harmonicGroup.add(arrow);
    }

    sceneRef.current = scene;
    return scene;
  }, []);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth;
    const height = container.clientHeight;

    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 100);
    camera.position.set(0, 5, 10);
    camera.lookAt(0, 0, 0);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const scene = buildScene();

    const animate = () => {
      frameRef.current = requestAnimationFrame(animate);

      if (autoRotate && groupRef.current) {
        rotRef.current.y += 0.003;
      }
      if (groupRef.current) {
        groupRef.current.rotation.x = rotRef.current.x;
        groupRef.current.rotation.y = rotRef.current.y;
      }

      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(frameRef.current);
      window.removeEventListener("resize", handleResize);
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [buildScene, autoRotate]);

  // Update layer visibility
  useEffect(() => {
    const g = layerGroupsRef.current;
    if (!g.exact) return;
    g.exact.visible = activeLayer === "all" || activeLayer === "exact";
    g.coexact.visible = activeLayer === "all" || activeLayer === "coexact";
    g.harmonic.visible = activeLayer === "all" || activeLayer === "harmonic";
  }, [activeLayer]);

  // Mouse drag rotation
  const onMouseDown = (e) => {
    mouseRef.current = { down: true, x: e.clientX, y: e.clientY };
    setAutoRotate(false);
  };
  const onMouseMove = (e) => {
    if (!mouseRef.current.down) return;
    const dx = e.clientX - mouseRef.current.x;
    const dy = e.clientY - mouseRef.current.y;
    rotRef.current.y += dx * 0.005;
    rotRef.current.x += dy * 0.005;
    rotRef.current.x = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, rotRef.current.x));
    mouseRef.current.x = e.clientX;
    mouseRef.current.y = e.clientY;
  };
  const onMouseUp = () => { mouseRef.current.down = false; };

  const layers = [
    { id: "all", label: "All Layers", color: "#e2e8f0" },
    { id: "exact", label: "dα  Exact (gradient)", color: "#3b82f6" },
    { id: "coexact", label: "δβ  Co-exact (curl)", color: "#ef4444" },
    { id: "harmonic", label: "γ   Harmonic (topology)", color: "#22c55e" },
  ];

  const descriptions = {
    all: "The Hodge Decomposition splits any flow ω on a compact manifold into three orthogonal parts: ω = dα + δβ + γ. Drag to rotate. Click a layer to isolate it.",
    exact: "The exact component dα is a gradient flow: wind moving from high to low pressure along a potential. It has zero curl. It pushes but doesn't spin. On the torus, the blue arrows flow between pressure zones.",
    coexact: "The co-exact component δβ is pure curl: tight local vortices that spin in place. This flow has zero divergence. It swirls but goes nowhere. The red arrows show spinning circulation patterns on the surface.",
    harmonic: "The harmonic component γ has zero curl AND zero divergence. It arises purely from the topology of the shape. The green arrows trace two independent loops: one around the hole (Loop 1) and one through it (Loop 2). On a sphere these would not exist.",
  };

  return (
    <div style={{ width: "100%", height: "100vh", background: "#0a0a14", display: "flex", flexDirection: "column", fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace" }}>
      <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600&display=swap" rel="stylesheet" />

      {/* Header */}
      <div style={{ padding: "16px 20px", borderBottom: "1px solid #1a1a2e" }}>
        <div style={{ fontSize: 10, letterSpacing: 3, color: "#4a5568", textTransform: "uppercase", marginBottom: 4 }}>
          Differential Geometry
        </div>
        <div style={{ fontSize: 20, fontWeight: 600, color: "#e2e8f0", letterSpacing: -0.5 }}>
          Hodge Decomposition on <span style={{ color: "#a78bfa" }}>T²</span>
        </div>
        <div style={{ fontSize: 13, color: "#64748b", marginTop: 4, fontWeight: 300 }}>
          ω = <span style={{ color: "#3b82f6" }}>dα</span> + <span style={{ color: "#ef4444" }}>δβ</span> + <span style={{ color: "#22c55e" }}>γ</span>
        </div>
      </div>

      {/* Layer controls */}
      <div style={{ display: "flex", gap: 6, padding: "10px 20px", flexWrap: "wrap" }}>
        {layers.map((l) => (
          <button
            key={l.id}
            onClick={() => setActiveLayer(l.id)}
            style={{
              padding: "5px 12px",
              borderRadius: 4,
              border: activeLayer === l.id ? `1px solid ${l.color}` : "1px solid #1a1a2e",
              background: activeLayer === l.id ? `${l.color}15` : "transparent",
              color: activeLayer === l.id ? l.color : "#4a5568",
              fontSize: 11,
              fontFamily: "inherit",
              cursor: "pointer",
              transition: "all 0.2s",
            }}
          >
            {l.label}
          </button>
        ))}
        <button
          onClick={() => setAutoRotate(!autoRotate)}
          style={{
            marginLeft: "auto",
            padding: "5px 12px",
            borderRadius: 4,
            border: "1px solid #1a1a2e",
            background: autoRotate ? "rgba(167,139,250,0.1)" : "transparent",
            color: autoRotate ? "#a78bfa" : "#4a5568",
            fontSize: 11,
            fontFamily: "inherit",
            cursor: "pointer",
          }}
        >
          {autoRotate ? "⟳ rotating" : "⟳ paused"}
        </button>
      </div>

      {/* 3D viewport */}
      <div
        ref={mountRef}
        style={{ flex: 1, cursor: "grab", minHeight: 300 }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      />

      {/* Description panel */}
      <div style={{
        padding: "14px 20px",
        borderTop: "1px solid #1a1a2e",
        fontSize: 12,
        color: "#94a3b8",
        lineHeight: 1.7,
        fontWeight: 300,
        maxHeight: 100,
        overflow: "auto",
      }}>
        {descriptions[activeLayer]}
      </div>
    </div>
  );
}
