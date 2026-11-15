/* XAN SHOP V2 — Realistic Interactive 3D Isometric Virtual AI Office (Three.js + Canvas Fallback) */
(function () {
  "use strict";

  const ROOM_CAMERAS = {
    all: { pos: [0, 24.0, 31.2], target: [0, 0.2, 2.2] },
    top: { pos: [0, 34.5, 1.8], target: [0, 0, 1.4] },
    director: { pos: [-10.0, 7.6, 3.8], target: [-10.2, 1.0, -4.4] },
    insta_analyst: { pos: [-5.1, 7.4, 5.2], target: [-5.1, 1.0, -3.2] },
    skaut: { pos: [-10.2, 7.8, 11.4], target: [-10.2, 1.0, 3.2] },
    smm_manager: { pos: [-3.5, 7.2, 5.0], target: [-3.5, 1.1, -4.2] },
    briefing: { pos: [-2.0, 8.2, 12.2], target: [-2.0, 1.0, 3.5] },
    sales_stylist: { pos: [3.6, 7.4, 7.0], target: [3.6, 1.1, -3.8] },
    video_employee: { pos: [2.2, 7.2, 6.4], target: [2.2, 1.1, -4.2] },
    accountant: { pos: [10.6, 7.4, 5.8], target: [10.6, 1.1, -4.0] },
    cargo_logistics: { pos: [7.6, 8.0, 12.6], target: [7.6, 1.0, 3.8] },
    server: { pos: [12.0, 6.5, 11.0], target: [11.6, 1.2, 4.4] },
    lounge: { pos: [0.2, 7.6, 18.4], target: [0.0, 0.9, 10.6] },
  };

  const AGENT_DEFS = [
    {
      id: "director",
      label: "Boshqaruvchi AI",
      role: "Avtonom Direktor & Strateg",
      room: "director",
      desk: [-10.2, -4.6],
      briefPos: [-4.4, 3.5],
      color: 0xfbbf24,
      accent: "#fbbf24",
      accessory: "crown",
    },
    {
      id: "insta_analyst",
      label: "Insta Tahlilchi",
      role: "Raqobatchi (@_tima_shop) & Reels Analitik",
      room: "insta_analyst",
      desk: [-5.1, -3.2],
      briefPos: [-3.9, 2.7],
      color: 0xec4899,
      accent: "#ec4899",
      accessory: "visor",
    },
    {
      id: "skaut",
      label: "Trend Skaut",
      role: "Pinduoduo & Bozor Tahlili",
      room: "skaut",
      desk: [-10.2, 2.8],
      briefPos: [-3.3, 1.7],
      color: 0x38bdf8,
      accent: "#38bdf8",
      accessory: "visor",
    },
    {
      id: "smm_manager",
      label: "SMM Agent",
      role: "Instagram & Telegram Kontent",
      room: "smm_manager",
      desk: [-3.6, -4.4],
      briefPos: [-1.1, 1.6],
      color: 0xf43f5e,
      accent: "#f43f5e",
      accessory: "cap",
    },
    {
      id: "video_employee",
      label: "Reels Studio",
      role: "Video Montaj & Ovoz (TTS)",
      room: "video_employee",
      desk: [1.8, -4.2],
      briefPos: [0.4, 2.8],
      color: 0xa855f7,
      accent: "#a855f7",
      accessory: "headphones",
    },
    {
      id: "sales_stylist",
      label: "Sotuv Stilist",
      role: "Mijozlar & Look Komplekt",
      room: "sales_stylist",
      desk: [5.4, -3.4],
      briefPos: [0.4, 4.4],
      color: 0x10b981,
      accent: "#10b981",
      accessory: "blazer",
    },
    {
      id: "accountant",
      label: "Hisobchi AI",
      role: "HUMO/UZCARD & Narx Auditi",
      room: "accountant",
      desk: [10.6, -4.0],
      briefPos: [-1.3, 5.4],
      color: 0x22c55e,
      accent: "#22c55e",
      accessory: "shield",
    },
    {
      id: "cargo_logistics",
      label: "Kargo & Bojxona",
      role: "TUJJOR-AVIA & YaTT Rejasi",
      room: "cargo_logistics",
      desk: [7.2, 3.6],
      briefPos: [-3.5, 5.2],
      color: 0xf97316,
      accent: "#f97316",
      accessory: "helmet",
    },
  ];

  const WORKFLOW_EDGES = [
    ["director", "insta_analyst"],
    ["insta_analyst", "skaut"],
    ["skaut", "video_employee"],
    ["video_employee", "smm_manager"],
    ["smm_manager", "sales_stylist"],
    ["sales_stylist", "accountant"],
    ["accountant", "cargo_logistics"],
    ["director", "accountant"],
  ];

  function createCanvasDrawer(w = 512, h = 256) {
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    const texture = new THREE.CanvasTexture(canvas);
    return { canvas, ctx, texture };
  }

  function createVirtualOffice(containerId, labelsId, opts = {}) {
    const canvas = document.getElementById(containerId);
    const labelsLayer = document.getElementById(labelsId);
    if (!canvas || !labelsLayer) return null;

    const onSelectAgent = opts.onSelectAgent || (() => {});
    const onWallAction = opts.onWallAction || (() => {});

    let renderer = null;
    try {
      if (typeof THREE !== "undefined") {
        renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
      }
    } catch (_e) {
      renderer = null;
    }

    if (!renderer) {
      return create2DFallbackOffice(canvas, labelsLayer, onSelectAgent);
    }

    const parent = canvas.parentElement;
    const width = Math.max(parent.clientWidth, 400);
    const height = Math.max(parent.clientHeight, 360);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(width, height, false);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x050b1d);
    scene.fog = new THREE.FogExp2(0x050b1d, 0.0085);

    const camera = new THREE.PerspectiveCamera(34, width / height, 0.1, 160);
    const camPos = new THREE.Vector3(...ROOM_CAMERAS.all.pos);
    const camTarget = new THREE.Vector3(...ROOM_CAMERAS.all.target);
    const goalPos = camPos.clone();
    const goalTarget = camTarget.clone();
    camera.position.copy(camPos);
    camera.lookAt(camTarget);

    // Rich Studio & Warm Terrace Illumination
    const hemi = new THREE.HemisphereLight(0xe0f2fe, 0x0f172a, 0.96);
    scene.add(hemi);

    const sun = new THREE.DirectionalLight(0xfff7ed, 1.08);
    sun.position.set(18, 30, 19);
    sun.castShadow = true;
    sun.shadow.mapSize.width = 2048;
    sun.shadow.mapSize.height = 2048;
    sun.shadow.camera.near = 4;
    sun.shadow.camera.far = 80;
    sun.shadow.camera.left = -22;
    sun.shadow.camera.right = 22;
    sun.shadow.camera.top = 18;
    sun.shadow.camera.bottom = -18;
    sun.shadow.bias = -0.0004;
    scene.add(sun);

    const studioCyan = new THREE.PointLight(0x38bdf8, 0.55, 48);
    studioCyan.position.set(-14, 9, -9);
    scene.add(studioCyan);

    const loungeWarm = new THREE.PointLight(0xfbbf24, 0.65, 18);
    loungeWarm.position.set(0.0, 3.2, 10.6);
    scene.add(loungeWarm);

    // Subtle Infinite Courtyard Grid & Twilight City Skyline Backdrop
    const gridHelper = new THREE.GridHelper(90, 60, 0x1e3a8a, 0x0b193d);
    gridHelper.position.y = -0.55;
    scene.add(gridHelper);

    const skyMat = new THREE.MeshStandardMaterial({ color: 0x0b152c, roughness: 0.7, metalness: 0.2 });
    const winGlowMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.25 });
    const warmWinMat = new THREE.MeshBasicMaterial({ color: 0xfde68a, transparent: true, opacity: 0.22 });
    [
      [-26, -18, 4.5, 14, 4.5],
      [-18, -22, 5.2, 20, 5.0],
      [-8, -24, 4.0, 16, 4.0],
      [4, -23, 5.5, 22, 5.0],
      [16, -21, 4.6, 17, 4.8],
      [26, -17, 4.8, 13, 4.4],
      [-28, 3, 4.2, 12, 5.2],
      [28, 4, 4.4, 15, 4.6],
    ].forEach(([tx, tz, tw, th, td], idx) => {
      const tower = new THREE.Mesh(new THREE.BoxGeometry(tw, th, td), skyMat);
      tower.position.set(tx, th / 2 - 0.55, tz);
      scene.add(tower);
      for (let floor = 0; floor < 4; floor++) {
        const strip = new THREE.Mesh(
          new THREE.BoxGeometry(tw * 0.72, 0.22, td + 0.06),
          (idx + floor) % 2 === 0 ? winGlowMat : warmWinMat
        );
        strip.position.set(tx, 2.2 + floor * 2.6, tz);
        scene.add(strip);
      }
    });

    // Outer Architectural Rooftop Terrace Deck + Timber Walkways
    const terraceDeck = new THREE.Mesh(
      new THREE.BoxGeometry(34.6, 0.28, 22.8),
      new THREE.MeshStandardMaterial({ color: 0x172136, roughness: 0.85 })
    );
    terraceDeck.position.set(0, -0.41, 1.5);
    terraceDeck.receiveShadow = true;
    scene.add(terraceDeck);

    // Timber Perimeter Promenade
    const woodDeckMat = new THREE.MeshStandardMaterial({ color: 0x7c5838, roughness: 0.75 });
    const bridgeWalk = new THREE.Mesh(new THREE.BoxGeometry(3.4, 0.1, 3.2), woodDeckMat);
    bridgeWalk.position.set(-1.6, -0.22, 8.2);
    bridgeWalk.receiveShadow = true;
    scene.add(bridgeWalk);

    // Subtle Cyan Perimeter Edge Strip around the Studio Platform
    const neonTrimMat = new THREE.MeshStandardMaterial({
      color: 0x0ea5e9,
      emissive: 0x0ea5e9,
      emissiveIntensity: 0.48,
    });
    const plinth = new THREE.Mesh(
      new THREE.BoxGeometry(27.8, 0.42, 16.0),
      new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.65 })
    );
    plinth.position.set(0, -0.22, 0);
    plinth.receiveShadow = true;
    scene.add(plinth);

    const plinthLed = new THREE.Mesh(new THREE.BoxGeometry(27.9, 0.06, 16.1), neonTrimMat);
    plinthLed.position.set(0, -0.36, 0);
    scene.add(plinthLed);

    function addFloorTile(x, z, w, d, color) {
      const m = new THREE.Mesh(
        new THREE.BoxGeometry(w, 0.06, d),
        new THREE.MeshStandardMaterial({ color, roughness: 0.52, metalness: 0.05 })
      );
      m.position.set(x, 0.02, z);
      m.receiveShadow = true;
      scene.add(m);
    }

    // Room Floors (Real Oak, Cool Marble & Studio Tiles)
    addFloorTile(-10.1, -4.3, 6.4, 6.2, 0xdbe5f4); // Boshqaruv
    addFloorTile(-10.1, 3.3, 6.4, 8.2, 0xd4b28a);  // Skaut
    addFloorTile(-3.5, -4.3, 6.4, 6.2, 0xd4b28a);  // Marketing
    addFloorTile(-2.0, 3.3, 9.2, 8.2, 0xcbd5e1);   // Majlislar zali
    addFloorTile(3.6, -4.1, 7.2, 6.6, 0xd0e2ff);   // Studio & Sotuv
    addFloorTile(10.5, -4.1, 5.8, 6.6, 0xdce6f5);  // Moliya
    addFloorTile(8.1, 3.3, 10.6, 8.2, 0xc8d4e6);   // Ombor & Server

    // Exterior Front Circular Rooftop Zone ("3-chi Doira Zona: Dam Olish & Moda Vitrinasi")
    const rotundaBase = new THREE.Mesh(
      new THREE.CylinderGeometry(3.85, 4.0, 0.34, 40),
      new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.55 })
    );
    rotundaBase.position.set(0.0, -0.18, 10.8);
    rotundaBase.receiveShadow = true;
    scene.add(rotundaBase);

    const rotundaEdge = new THREE.Mesh(
      new THREE.TorusGeometry(3.92, 0.05, 10, 48),
      neonTrimMat
    );
    rotundaEdge.rotation.x = Math.PI / 2;
    rotundaEdge.position.set(0.0, -0.02, 10.8);
    scene.add(rotundaEdge);

    const rotundaFloor = new THREE.Mesh(
      new THREE.CylinderGeometry(3.55, 3.55, 0.06, 40),
      new THREE.MeshStandardMaterial({ color: 0xe2cfb6, roughness: 0.7 })
    );
    rotundaFloor.position.set(0.0, 0.02, 10.8);
    rotundaFloor.receiveShadow = true;
    scene.add(rotundaFloor);

    const rotundaRug = new THREE.Mesh(
      new THREE.CylinderGeometry(2.15, 2.15, 0.03, 32),
      new THREE.MeshStandardMaterial({ color: 0x0f766e, roughness: 0.9 })
    );
    rotundaRug.position.set(0.0, 0.06, 10.8);
    rotundaRug.receiveShadow = true;
    scene.add(rotundaRug);

    const trimMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.4, metalness: 0.35 });
    const woodFurnitureMat = new THREE.MeshStandardMaterial({ color: 0x5c4033, roughness: 0.55 });

    // Lounge Coffee Table + Espresso Cups + Curved Armchairs
    const coffeeTable = new THREE.Mesh(
      new THREE.CylinderGeometry(0.72, 0.72, 0.06, 24),
      new THREE.MeshPhysicalMaterial({ color: 0xbae6fd, transparent: true, opacity: 0.55, roughness: 0.1 })
    );
    coffeeTable.position.set(-0.2, 0.48, 10.8);
    scene.add(coffeeTable);
    const coffeeLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.25, 0.44, 12), trimMat);
    coffeeLeg.position.set(-0.2, 0.24, 10.8);
    scene.add(coffeeLeg);

    [[-0.4, 10.65], [0.05, 10.95]].forEach(([cx, cz]) => {
      const cup = new THREE.Mesh(
        new THREE.CylinderGeometry(0.06, 0.05, 0.11, 10),
        new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.3 })
      );
      cup.position.set(cx, 0.56, cz);
      scene.add(cup);
    });

    // Two Designer Lounge Chairs + Fashion Display Mannequin on Pedestal
    [[-1.65, 10.7, 1.2], [1.25, 11.4, -2.1]].forEach(([cx, cz, ry]) => {
      const chair = new THREE.Group();
      const cushion = new THREE.Mesh(
        new THREE.BoxGeometry(0.9, 0.24, 0.8),
        new THREE.MeshStandardMaterial({ color: 0xf59e0b, roughness: 0.75 })
      );
      cushion.position.y = 0.28;
      cushion.castShadow = true;
      chair.add(cushion);
      const back = new THREE.Mesh(
        new THREE.BoxGeometry(0.9, 0.52, 0.18),
        new THREE.MeshStandardMaterial({ color: 0xd97706, roughness: 0.75 })
      );
      back.position.set(0, 0.55, -0.32);
      chair.add(back);
      chair.position.set(cx, 0.04, cz);
      chair.rotation.y = ry;
      scene.add(chair);
    });

    // Illuminated Boutique Showroom Pedestal inside Rotunda (Fashion Identity!)
    [2.1, -2.2].forEach((mx, i) => {
      const mz = i === 0 ? 9.8 : 9.7;
      const ped = new THREE.Mesh(
        new THREE.CylinderGeometry(0.45, 0.5, 0.45, 18),
        new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.35, metalness: 0.4 })
      );
      ped.position.set(mx, 0.26, mz);
      scene.add(ped);
      const torso = new THREE.Mesh(
        new THREE.CylinderGeometry(0.22, 0.18, 0.72, 14),
        new THREE.MeshStandardMaterial({ color: i === 0 ? 0x1e293b : 0x78716c, roughness: 0.65 })
      );
      torso.position.set(mx, 0.96, mz);
      torso.castShadow = true;
      scene.add(torso);
      const stand = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.3, 8), trimMat);
      stand.position.set(mx, 0.58, mz);
      scene.add(stand);
    });

    // Perimeter & Glass Divider Walls
    const wallMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.4 });
    const glassMat = new THREE.MeshPhysicalMaterial({
      color: 0x93c5fd,
      transparent: true,
      opacity: 0.21,
      roughness: 0.1,
    });

    function addWall(x, z, w, h, d, isGlass = false) {
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), isGlass ? glassMat : wallMat);
      mesh.position.set(x, h / 2, z);
      mesh.castShadow = !isGlass;
      mesh.receiveShadow = true;
      scene.add(mesh);
      if (!isGlass) {
        const cap = new THREE.Mesh(new THREE.BoxGeometry(w + 0.04, 0.08, d + 0.04), trimMat);
        cap.position.set(x, h + 0.04, z);
        scene.add(cap);
      }
    }

    // Back & Side Perimeter Walls
    addWall(0, -7.7, 27.6, 2.35, 0.25);
    addWall(-13.6, 0, 0.25, 2.35, 15.6);
    addWall(13.6, 0, 0.25, 2.35, 15.6);
    // Split front glass barrier leaving clean central walkway to the Rotunda
    addWall(-8.6, 7.7, 10.2, 0.78, 0.14, true);
    addWall(7.1, 7.7, 13.0, 0.78, 0.14, true);

    // Interior Glass Dividers
    addWall(-6.8, -4.2, 0.1, 1.9, 6.6, true);
    addWall(-0.2, -4.2, 0.1, 1.9, 6.6, true);
    addWall(7.3, -4.2, 0.1, 1.9, 6.6, true);
    addWall(-6.8, 3.2, 0.1, 1.9, 8.2, true);
    addWall(2.7, 3.2, 0.1, 1.9, 8.2, true);
    addWall(10.0, 3.2, 0.1, 2.0, 8.2, true);
    addWall(0, -0.9, 27.0, 1.15, 0.1, true);

    // Architectural Skylight Ceiling Beams & Warm Suspended Pendant Lamps over Majlis
    [-2.0, 3.5].forEach((bz) => {
      const beam = new THREE.Mesh(new THREE.BoxGeometry(27.2, 0.08, 0.12), trimMat);
      beam.position.set(0, 2.48, bz);
      scene.add(beam);
    });
    [-3.4, -2.0, -0.6].forEach((px) => {
      const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.55, 6), trimMat);
      cord.position.set(px, 2.2, 3.5);
      scene.add(cord);
      const shade = new THREE.Mesh(
        new THREE.CylinderGeometry(0.08, 0.22, 0.14, 14),
        new THREE.MeshStandardMaterial({ color: 0xfef3c7, emissive: 0xfde68a, emissiveIntensity: 0.75 })
      );
      shade.position.set(px, 1.92, 3.5);
      scene.add(shade);
    });

    // Panoramic twilight windows
    [-10.2, -3.5, 3.6, 10.5].forEach((wx) => {
      const win = new THREE.Mesh(
        new THREE.BoxGeometry(2.3, 1.25, 0.08),
        new THREE.MeshStandardMaterial({ color: 0x0f172a, emissive: 0x0ea5e9, emissiveIntensity: 0.22 })
      );
      win.position.set(wx, 1.35, -7.54);
      scene.add(win);
    });

    // Helper: Workstations
    const monitorScreenMat = new THREE.MeshStandardMaterial({
      color: 0x0b1635,
      emissive: 0x38bdf8,
      emissiveIntensity: 0.45,
    });
    function addWorkstation(x, z, rotY = 0, deskTint = 0xf8fafc) {
      const g = new THREE.Group();
      const deskTop = new THREE.Mesh(
        new THREE.BoxGeometry(1.75, 0.08, 0.85),
        new THREE.MeshStandardMaterial({ color: deskTint, roughness: 0.35 })
      );
      deskTop.position.y = 0.72;
      deskTop.castShadow = true;
      deskTop.receiveShadow = true;
      g.add(deskTop);

      [-0.75, 0.75].forEach((lx) => {
        const leg = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.72, 0.72), trimMat);
        leg.position.set(lx, 0.36, 0);
        g.add(leg);
      });

      [-0.38, 0.38].forEach((mx) => {
        const scr = new THREE.Mesh(new THREE.BoxGeometry(0.66, 0.42, 0.05), monitorScreenMat);
        scr.position.set(mx, 1.04, -0.22);
        scr.castShadow = true;
        g.add(scr);
        const stand = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.2, 0.06), trimMat);
        stand.position.set(mx, 0.82, -0.22);
        g.add(stand);
      });

      const seat = new THREE.Mesh(new THREE.BoxGeometry(0.54, 0.08, 0.52), trimMat);
      seat.position.set(0, 0.45, 0.58);
      g.add(seat);
      const back = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.58, 0.08), trimMat);
      back.position.set(0, 0.76, 0.82);
      g.add(back);

      g.position.set(x, 0, z);
      g.rotation.y = rotY;
      scene.add(g);
    }

    // Executive Walnut Desk for CEO + Standard Desks
    addWorkstation(-10.2, -5.0, 0, 0x92623a);
    addWorkstation(-10.2, 2.4);
    addWorkstation(-11.2, 4.8);
    addWorkstation(-3.6, -5.0);
    addWorkstation(-5.1, -3.2);
    addWorkstation(-2.0, -3.2);
    addWorkstation(1.8, -4.8);
    addWorkstation(5.4, -4.0);
    addWorkstation(5.4, -2.0);
    addWorkstation(10.6, -4.6);
    addWorkstation(7.2, 3.0);

    // Floating Golden Holographic Market Globe on CEO Desk
    const ceoGlobe = new THREE.Mesh(
      new THREE.IcosahedronGeometry(0.24, 1),
      new THREE.MeshStandardMaterial({
        color: 0xfbbf24,
        emissive: 0xf59e0b,
        emissiveIntensity: 0.6,
        wireframe: true,
      })
    );
    ceoGlobe.position.set(-11.4, 1.15, -5.0);
    scene.add(ceoGlobe);

    // Center Majlislar Zali: Emerald Carpet + Oval Table
    const rug = new THREE.Mesh(
      new THREE.BoxGeometry(6.8, 0.05, 5.6),
      new THREE.MeshStandardMaterial({ color: 0x065f46, roughness: 0.9 })
    );
    rug.position.set(-2.0, 0.05, 3.5);
    rug.receiveShadow = true;
    scene.add(rug);

    const confTable = new THREE.Mesh(
      new THREE.CylinderGeometry(2.1, 2.1, 0.1, 28),
      new THREE.MeshStandardMaterial({ color: 0xf1f5f9, roughness: 0.3 })
    );
    confTable.scale.set(1.0, 1.0, 1.45);
    confTable.position.set(-2.0, 0.74, 3.5);
    confTable.castShadow = true;
    confTable.receiveShadow = true;
    scene.add(confTable);

    const confBase = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 0.9, 0.7, 16), trimMat);
    confBase.position.set(-2.0, 0.36, 3.5);
    scene.add(confBase);

    // Live Animated Wall Presentation Screen
    const liveScreen = createCanvasDrawer(512, 256);
    function redrawLiveScreen(tickVal) {
      const { ctx, texture } = liveScreen;
      ctx.fillStyle = "#081229";
      ctx.fillRect(0, 0, 512, 256);
      ctx.fillStyle = "#38bdf8";
      ctx.font = "bold 26px Inter, sans-serif";
      ctx.fillText("XAN SHOP • STRATEGIK AI SHTAB", 26, 48);
      ctx.fillStyle = "#94a3b8";
      ctx.font = "17px Inter, sans-serif";
      ctx.fillText("50k/100k yaxlitlash | 5–10 kun Avia | $200/YaTT", 26, 80);
      const baseBars = [110, 158, 95, 192, 165, 208];
      baseBars.forEach((v, i) => {
        const wave = Math.sin(tickVal * 1.4 + i * 0.8) * 14;
        const h = Math.max(40, (v + wave) * 0.55);
        ctx.fillStyle = i % 2 === 0 ? "#38bdf8" : "#10b981";
        ctx.fillRect(42 + i * 72, 232 - h, 42, h);
      });
      texture.needsUpdate = true;
    }
    redrawLiveScreen(0);

    const confBoard = new THREE.Mesh(
      new THREE.BoxGeometry(3.2, 1.45, 0.12),
      new THREE.MeshStandardMaterial({ map: liveScreen.texture, emissive: 0x0f172a })
    );
    confBoard.position.set(-2.0, 1.55, -0.78);
    scene.add(confBoard);

    // Marketing Wall: Colorful Kanban Doska
    const kanbanDrawer = createCanvasDrawer(512, 256);
    (function drawKanban() {
      const { ctx, texture } = kanbanDrawer;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, 512, 256);
      ctx.strokeStyle = "#1e293b";
      ctx.lineWidth = 10;
      ctx.strokeRect(5, 5, 502, 246);
      const cols = ["#f43f5e", "#f59e0b", "#38bdf8", "#10b981"];
      cols.forEach((col, cIdx) => {
        for (let r = 0; r < 3; r++) {
          ctx.fillStyle = col;
          ctx.fillRect(28 + cIdx * 116, 30 + r * 66, 94, 48);
        }
      });
      texture.needsUpdate = true;
    })();
    const kanbanMesh = new THREE.Mesh(
      new THREE.BoxGeometry(0.12, 1.45, 2.7),
      new THREE.MeshStandardMaterial({ map: kanbanDrawer.texture })
    );
    kanbanMesh.position.set(-6.68, 1.32, -4.3);
    scene.add(kanbanMesh);

    const mktChartMesh = new THREE.Mesh(
      new THREE.BoxGeometry(2.6, 1.2, 0.1),
      new THREE.MeshStandardMaterial({ map: liveScreen.texture, emissive: 0x0ea5e9, emissiveIntensity: 0.25 })
    );
    mktChartMesh.position.set(-3.5, 1.45, -7.48);
    scene.add(mktChartMesh);

    // Reels Studio & Fashion Clothing Rack Props
    const greenScreen = new THREE.Mesh(
      new THREE.BoxGeometry(1.85, 1.75, 0.08),
      new THREE.MeshStandardMaterial({ color: 0x10b981, emissive: 0x059669, emissiveIntensity: 0.25 })
    );
    greenScreen.position.set(1.2, 0.88, -7.35);
    scene.add(greenScreen);

    const ringLight = new THREE.Mesh(
      new THREE.TorusGeometry(0.32, 0.05, 12, 28),
      new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xfef08a, emissiveIntensity: 0.95 })
    );
    ringLight.position.set(2.4, 1.55, -6.1);
    scene.add(ringLight);
    const tripod = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.04, 1.5, 8), trimMat);
    tripod.position.set(2.4, 0.75, -6.1);
    scene.add(tripod);

    // Fashion Wardrobe Rack inside Studio & Sotuv!
    const rackGroup = new THREE.Group();
    const rackBar = new THREE.Mesh(
      new THREE.CylinderGeometry(0.03, 0.03, 2.0, 10),
      new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.8, roughness: 0.2 })
    );
    rackBar.rotation.z = Math.PI / 2;
    rackBar.position.y = 1.45;
    rackGroup.add(rackBar);
    [-0.95, 0.95].forEach((rx) => {
      const post = new THREE.Mesh(new THREE.CylinderGeometry(0.028, 0.035, 1.45, 8), trimMat);
      post.position.set(rx, 0.72, 0);
      rackGroup.add(post);
    });
    [0x1e293b, 0xa8a29e, 0x3f6212, 0x7c2d12, 0x334155].forEach((cHex, i) => {
      const garment = new THREE.Mesh(
        new THREE.BoxGeometry(0.28, 0.68, 0.42),
        new THREE.MeshStandardMaterial({ color: cHex, roughness: 0.8 })
      );
      garment.position.set(-0.68 + i * 0.34, 1.05, 0);
      garment.castShadow = true;
      rackGroup.add(garment);
    });
    rackGroup.position.set(4.1, 0, -6.7);
    scene.add(rackGroup);

    // Warehouse Shelving & Cargo Parcels (Ombor)
    [4.4, 6.2].forEach((sx) => {
      const rack = new THREE.Mesh(
        new THREE.BoxGeometry(1.2, 2.0, 3.6),
        new THREE.MeshStandardMaterial({ color: 0x334155, metalness: 0.5, roughness: 0.4 })
      );
      rack.position.set(sx, 1.0, 5.2);
      rack.castShadow = true;
      scene.add(rack);
      [0.45, 1.15, 1.75].forEach((py, idx) => {
        const parcel = new THREE.Mesh(
          new THREE.BoxGeometry(0.9, 0.42, 0.95),
          new THREE.MeshStandardMaterial({ color: idx % 2 === 0 ? 0xd97706 : 0xb45309, roughness: 0.8 })
        );
        parcel.position.set(sx, py, 4.4 + (idx % 2) * 1.3);
        scene.add(parcel);
      });
    });

    // Server Room Racks + Blinking LEDs
    const serverLeds = [];
    [11.0, 12.3].forEach((rx) => {
      const rack = new THREE.Mesh(
        new THREE.BoxGeometry(0.95, 2.2, 1.35),
        new THREE.MeshStandardMaterial({ color: 0x090f1d, metalness: 0.6, roughness: 0.3 })
      );
      rack.position.set(rx, 1.1, 4.6);
      rack.castShadow = true;
      scene.add(rack);
      for (let row = 0; row < 5; row++) {
        const led = new THREE.Mesh(
          new THREE.BoxGeometry(0.55, 0.06, 0.05),
          new THREE.MeshStandardMaterial({
            color: row % 2 === 0 ? 0x10b981 : 0x38bdf8,
            emissive: row % 2 === 0 ? 0x10b981 : 0x38bdf8,
            emissiveIntensity: 0.9,
          })
        );
        led.position.set(rx, 0.45 + row * 0.35, 3.91);
        scene.add(led);
        serverLeds.push(led);
      }
    });

    // Indoor Plants + Lush Exterior Terrace Trees & Glowing Bollard Lamps
    function addPlant(px, pz, scale = 1.0, darkWood = false) {
      const pg = new THREE.Group();
      const pot = new THREE.Mesh(
        new THREE.CylinderGeometry(0.28 * scale, 0.22 * scale, 0.45 * scale, 12),
        darkWood ? woodFurnitureMat : new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.6 })
      );
      pot.position.y = 0.22 * scale;
      pg.add(pot);
      const leaves = new THREE.Mesh(
        new THREE.DodecahedronGeometry(0.46 * scale, 1),
        new THREE.MeshStandardMaterial({ color: 0x16a34a, roughness: 0.7 })
      );
      leaves.position.y = 0.78 * scale;
      leaves.castShadow = true;
      pg.add(leaves);
      pg.position.set(px, 0, pz);
      scene.add(pg);
    }

    [
      [-12.8, -6.9, 1.0, false], [-7.4, -6.9, 0.95, false], [-12.8, 6.8, 1.0, false], [-0.8, -6.9, 0.9, false],
      [6.6, -6.9, 0.95, false], [12.8, -6.9, 1.0, false], [3.3, 0.4, 0.85, false], [9.3, 6.8, 1.0, false],
      // Terrace garden trees
      [-15.6, -6.2, 1.45, true], [-15.6, 2.2, 1.45, true], [-15.2, 9.6, 1.4, true],
      [15.6, -6.2, 1.45, true], [15.6, 2.4, 1.45, true], [15.2, 9.6, 1.4, true],
      [-5.6, 10.6, 1.15, true], [5.6, 10.6, 1.15, true],
    ].forEach(([px, pz, sc, dw]) => addPlant(px, pz, sc, dw));

    // Terrace Warm Architectural Bollard Lamps
    [[-15.2, 5.8], [15.2, 5.8], [-4.2, 8.6], [4.2, 8.6]].forEach(([bx, bz]) => {
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.75, 0.14), trimMat);
      post.position.set(bx, 0.12, bz);
      scene.add(post);
      const bulb = new THREE.Mesh(
        new THREE.BoxGeometry(0.16, 0.18, 0.16),
        new THREE.MeshStandardMaterial({ color: 0xfef3c7, emissive: 0xf59e0b, emissiveIntensity: 0.9 })
      );
      bulb.position.set(bx, 0.56, bz);
      scene.add(bulb);
    });

    // Subtle Ambient Light Motes drifting over Studio
    const motes = [];
    const moteGeo = new THREE.SphereGeometry(0.055, 6, 6);
    const moteMat = new THREE.MeshBasicMaterial({ color: 0xbae6fd, transparent: true, opacity: 0.5 });
    for (let i = 0; i < 24; i++) {
      const m = new THREE.Mesh(moteGeo, moteMat);
      const baseX = (Math.random() - 0.5) * 28;
      const baseY = 1.4 + Math.random() * 3.0;
      const baseZ = (Math.random() - 0.5) * 20;
      m.position.set(baseX, baseY, baseZ);
      scene.add(m);
      motes.push({ mesh: m, baseX, baseY, baseZ, speed: 0.4 + Math.random() * 0.6, phase: Math.random() * 6.28 });
    }

    // Build Articulated Lifelike 3D Agent Meshes (with moving arms & executive props)
    const agentObjects = new Map();
    const clickableMeshes = [];

    AGENT_DEFS.forEach((def, idx) => {
      const root = new THREE.Group();
      root.userData.agentId = def.id;

      const bodyColor = def.accessory === "blazer" ? 0x1e293b : def.accessory === "crown" ? 0x0f172a : 0xf1f5f9;
      const body = new THREE.Mesh(
        new THREE.CylinderGeometry(0.28, 0.34, 0.72, 16),
        new THREE.MeshStandardMaterial({ color: bodyColor, roughness: 0.35 })
      );
      body.position.y = 0.56;
      body.castShadow = true;
      body.userData.agentId = def.id;
      root.add(body);
      clickableMeshes.push(body);

      const core = new THREE.Mesh(
        new THREE.BoxGeometry(0.22, 0.16, 0.08),
        new THREE.MeshStandardMaterial({ color: def.color, emissive: def.color, emissiveIntensity: 0.85 })
      );
      core.position.set(0, 0.64, 0.29);
      root.add(core);

      // Left & Right Articulated Arms for lifelike typing / briefing gestures
      const armGeo = new THREE.CylinderGeometry(0.06, 0.055, 0.44, 10);
      const armMat = new THREE.MeshStandardMaterial({ color: bodyColor, roughness: 0.4 });
      const leftArm = new THREE.Mesh(armGeo, armMat);
      leftArm.position.set(-0.37, 0.58, 0.06);
      leftArm.rotation.z = 0.18;
      root.add(leftArm);

      const rightArm = new THREE.Mesh(armGeo, armMat);
      rightArm.position.set(0.37, 0.58, 0.06);
      rightArm.rotation.z = -0.18;
      root.add(rightArm);

      const headColor = def.accessory === "blazer" ? 0xfde68a : 0xffffff;
      const head = new THREE.Mesh(
        new THREE.SphereGeometry(0.29, 18, 14),
        new THREE.MeshStandardMaterial({ color: headColor, roughness: 0.25 })
      );
      head.position.y = 1.15;
      head.castShadow = true;
      head.userData.agentId = def.id;
      root.add(head);
      clickableMeshes.push(head);

      const visor = new THREE.Mesh(
        new THREE.BoxGeometry(0.38, 0.14, 0.16),
        new THREE.MeshStandardMaterial({ color: 0x0f172a, emissive: def.color, emissiveIntensity: 0.65 })
      );
      visor.position.set(0, 1.16, 0.21);
      root.add(visor);

      if (def.accessory === "cap") {
        const cap = new THREE.Mesh(
          new THREE.SphereGeometry(0.31, 14, 10, 0, Math.PI * 2, 0, Math.PI * 0.52),
          new THREE.MeshStandardMaterial({ color: 0xef4444, roughness: 0.5 })
        );
        cap.position.y = 1.18;
        root.add(cap);
      } else if (def.accessory === "crown") {
        const halo = new THREE.Mesh(
          new THREE.TorusGeometry(0.24, 0.038, 8, 22),
          new THREE.MeshStandardMaterial({ color: 0xfbbf24, emissive: 0xf59e0b, emissiveIntensity: 0.8 })
        );
        halo.rotation.x = Math.PI / 2;
        halo.position.y = 1.56;
        root.add(halo);
      } else {
        const ant = new THREE.Mesh(
          new THREE.SphereGeometry(0.06, 8, 8),
          new THREE.MeshStandardMaterial({ color: def.color, emissive: def.color, emissiveIntensity: 0.9 })
        );
        ant.position.y = 1.52;
        root.add(ant);
      }

      const ring = new THREE.Mesh(
        new THREE.RingGeometry(0.42, 0.52, 24),
        new THREE.MeshBasicMaterial({ color: def.color, side: THREE.DoubleSide, transparent: true, opacity: 0.72 })
      );
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = 0.07;
      root.add(ring);

      root.position.set(def.desk[0], 0, def.desk[1] + 0.55);
      scene.add(root);

      const tag = document.createElement("button");
      tag.type = "button";
      tag.className = "agent-tag-3d";
      tag.innerHTML = `<span class="dot" style="background:${def.accent};box-shadow:0 0 8px ${def.accent}"></span><span>${def.label}</span>`;
      tag.onclick = () => selectAgent(def.id, true);
      labelsLayer.appendChild(tag);

      const bubble = document.createElement("div");
      bubble.className = "agent-bubble-3d";
      bubble.style.display = "none";
      labelsLayer.appendChild(bubble);

      agentObjects.set(def.id, {
        def,
        mesh: root,
        core,
        ring,
        leftArm,
        rightArm,
        tag,
        bubble,
        curX: def.desk[0],
        curZ: def.desk[1] + 0.55,
        status: "idle",
        task: "Tayyor",
        phase: idx * 0.9,
      });
    });

    // Interactive Wall & Zone Pins
    const wallPins = [
      { id: "doska", text: "📋 Doska", pos: new THREE.Vector3(-6.4, 2.25, -4.3) },
      { id: "reyting", text: "📊 Reyting", pos: new THREE.Vector3(3.6, 2.45, -7.2) },
      { id: "server", text: "🖥️ OmniRoute", pos: new THREE.Vector3(11.6, 2.55, 4.4) },
      { id: "lounge", text: "☕ Dam Olish & Vitrin", pos: new THREE.Vector3(0.0, 1.95, 10.8) },
    ].map((wp) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "room-badge-3d";
      btn.textContent = wp.text;
      btn.onclick = () => {
        if (wp.id === "lounge") focusRoom("lounge");
        else onWallAction(wp.id);
      };
      labelsLayer.appendChild(btn);
      return { ...wp, el: btn };
    });

    // Data Packet Arcs between collaborating departments
    const packets = WORKFLOW_EDGES.map(([fromId, toId], i) => {
      const m = new THREE.Mesh(
        new THREE.SphereGeometry(0.11, 10, 10),
        new THREE.MeshBasicMaterial({ color: fromId === "director" ? 0xfbbf24 : 0x38bdf8 })
      );
      scene.add(m);
      return { fromId, toId, mesh: m, t: i * 0.15 };
    });

    // Active CEO Command Pulse Ring + Executive Beams
    const ceoShockwave = new THREE.Mesh(
      new THREE.RingGeometry(0.6, 0.85, 32),
      new THREE.MeshBasicMaterial({ color: 0xfbbf24, side: THREE.DoubleSide, transparent: true, opacity: 0.0 })
    );
    ceoShockwave.rotation.x = -Math.PI / 2;
    ceoShockwave.position.set(-10.2, 0.14, -4.05);
    scene.add(ceoShockwave);
    let ceoPulseTimer = 0;

    function triggerCeoCommandPulse() {
      ceoPulseTimer = 6.0;
      focusRoom("all");
    }

    let selectedId = null;
    let briefingMode = false;
    let searchFilter = "";

    function selectAgent(id, focus = false) {
      selectedId = id;
      for (const [k, obj] of agentObjects.entries()) {
        obj.tag.classList.toggle("selected", k === id);
      }
      if (focus && id && ROOM_CAMERAS[id]) {
        focusRoom(id);
      } else if (focus && id) {
        const o = agentObjects.get(id);
        if (o) {
          goalTarget.set(o.curX, 1.0, o.curZ);
          goalPos.set(o.curX + 3.2, 6.2, o.curZ + 7.0);
        }
      }
      onSelectAgent(id);
    }

    function focusRoom(roomKey) {
      const preset = ROOM_CAMERAS[roomKey] || ROOM_CAMERAS.all;
      goalPos.set(...preset.pos);
      goalTarget.set(...preset.target);
    }

    function setBriefingMode(enabled) {
      briefingMode = Boolean(enabled);
      if (briefingMode) focusRoom("briefing");
      else focusRoom("all");
    }

    function setSearch(query) {
      searchFilter = String(query || "").trim().toLowerCase();
      for (const [id, obj] of agentObjects.entries()) {
        const hit =
          !searchFilter ||
          obj.def.label.toLowerCase().includes(searchFilter) ||
          obj.def.role.toLowerCase().includes(searchFilter) ||
          id.toLowerCase().includes(searchFilter);
        obj.tag.classList.toggle("dimmed", !hit);
        if (searchFilter && hit) {
          goalTarget.set(obj.curX, 1.0, obj.curZ);
          goalPos.set(obj.curX + 3.0, 6.8, obj.curZ + 7.2);
        }
      }
    }

    function updateState(stateData) {
      const list = (stateData && stateData.agents) || [];
      list.forEach((a) => {
        const obj = agentObjects.get(a.id);
        if (!obj) return;
        obj.status = a.status || "idle";
        obj.task = a.current_task || "Tayyor";
        if ((obj.status === "working" || String(obj.task).startsWith("📌")) && obj.task) {
          obj.bubble.textContent = obj.task.slice(0, 62);
          obj.bubble.style.display = "block";
        } else {
          obj.bubble.style.display = "none";
        }
        const dotEl = obj.tag.querySelector(".dot");
        if (dotEl) {
          const isBusy = obj.status === "working";
          dotEl.style.background = isBusy ? "#10b981" : "#38bdf8";
          dotEl.style.boxShadow = isBusy ? "0 0 10px #10b981" : "0 0 6px #38bdf8";
        }
      });
    }

    // Orbit Drag + Zoom + Raycast Pick
    let dragging = false;
    let dragMoved = 0;
    let prevX = 0;
    let prevY = 0;
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();

    canvas.addEventListener("pointerdown", (e) => {
      dragging = true;
      dragMoved = 0;
      prevX = e.clientX;
      prevY = e.clientY;
    });
    window.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const dx = e.clientX - prevX;
      const dy = e.clientY - prevY;
      dragMoved += Math.abs(dx) + Math.abs(dy);
      prevX = e.clientX;
      prevY = e.clientY;

      const offset = goalPos.clone().sub(goalTarget);
      const spherical = new THREE.Spherical().setFromVector3(offset);
      spherical.theta -= dx * 0.0055;
      spherical.phi = Math.max(0.28, Math.min(1.28, spherical.phi - dy * 0.0045));
      offset.setFromSpherical(spherical);
      goalPos.copy(goalTarget).add(offset);
    });
    window.addEventListener("pointerup", (e) => {
      if (!dragging) return;
      dragging = false;
      if (dragMoved < 6) {
        const rect = canvas.getBoundingClientRect();
        pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(pointer, camera);
        const hits = raycaster.intersectObjects(clickableMeshes, false);
        if (hits.length > 0 && hits[0].object.userData.agentId) {
          selectAgent(hits[0].object.userData.agentId, false);
        }
      }
    });
    canvas.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        const offset = goalPos.clone().sub(goalTarget);
        const len = offset.length();
        const nextLen = Math.max(7.5, Math.min(40, len + e.deltaY * 0.016));
        offset.setLength(nextLen);
        goalPos.copy(goalTarget).add(offset);
      },
      { passive: false }
    );

    function handleResize() {
      const w = Math.max(parent.clientWidth, 320);
      const h = Math.max(parent.clientHeight, 320);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    }
    window.addEventListener("resize", handleResize);

    const projVec = new THREE.Vector3();
    let rafId = null;
    const clock = new THREE.Clock();
    let screenTimer = 0;

    function animate() {
      rafId = requestAnimationFrame(animate);
      const dt = Math.min(clock.getDelta(), 0.05);
      const t = clock.elapsedTime;

      camPos.lerp(goalPos, 0.09);
      camTarget.lerp(goalTarget, 0.09);
      camera.position.copy(camPos);
      camera.lookAt(camTarget);

      // Update dynamic wall chart & CEO holo globe
      screenTimer += dt;
      if (screenTimer > 0.9) {
        screenTimer = 0;
        redrawLiveScreen(t);
      }
      ceoGlobe.rotation.y = t * 0.7;
      ceoGlobe.position.y = 1.16 + Math.sin(t * 2.0) * 0.06;

      // Floating warm skylight particles
      motes.forEach((m) => {
        m.mesh.position.y = m.baseY + Math.sin(t * m.speed + m.phase) * 0.32;
        m.mesh.position.x = m.baseX + Math.cos(t * 0.35 + m.phase) * 0.25;
      });

      // Server Blink LEDs
      serverLeds.forEach((led, idx) => {
        led.material.emissiveIntensity = 0.45 + 0.55 * Math.abs(Math.sin(t * 2.4 + idx));
      });

      // CEO Command Shockwave Pulse
      if (ceoPulseTimer > 0) {
        ceoPulseTimer = Math.max(0, ceoPulseTimer - dt);
        const dirObj = agentObjects.get("director");
        if (dirObj) {
          ceoShockwave.position.set(dirObj.curX, 0.12, dirObj.curZ);
        }
        const wave = ((6.0 - ceoPulseTimer) * 1.6) % 1.0;
        ceoShockwave.scale.setScalar(1.0 + wave * 12.0);
        ceoShockwave.material.opacity = (1.0 - wave) * 0.75;
      } else {
        ceoShockwave.material.opacity = 0;
      }

      const cw = canvas.clientWidth || parent.clientWidth;
      const ch = canvas.clientHeight || parent.clientHeight;

      for (const [id, obj] of agentObjects.entries()) {
        const destX = briefingMode ? obj.def.briefPos[0] : obj.def.desk[0];
        const destZ = briefingMode ? obj.def.briefPos[1] : obj.def.desk[1] + 0.55;
        obj.curX += (destX - obj.curX) * Math.min(1, dt * 3.2);
        obj.curZ += (destZ - obj.curZ) * Math.min(1, dt * 3.2);

        const isWorking = obj.status === "working";
        const bob = isWorking ? Math.abs(Math.sin(t * 6.5 + obj.phase)) * 0.08 : Math.sin(t * 2.1 + obj.phase) * 0.03;
        obj.mesh.position.set(obj.curX, bob, obj.curZ);

        // Lifelike arm gestures (typing or briefing gesture)
        if (briefingMode) {
          obj.mesh.lookAt(-2.0, bob, 3.5);
          obj.leftArm.rotation.x = -0.35 + Math.sin(t * 4.5 + obj.phase) * 0.25;
          obj.rightArm.rotation.x = -0.35 + Math.cos(t * 4.5 + obj.phase) * 0.25;
        } else if (isWorking) {
          obj.mesh.rotation.y = Math.sin(t * 1.1 + obj.phase) * 0.22;
          obj.leftArm.rotation.x = -0.75 + Math.sin(t * 9.0 + obj.phase) * 0.28;
          obj.rightArm.rotation.x = -0.75 + Math.cos(t * 9.0 + obj.phase) * 0.28;
        } else {
          obj.mesh.rotation.y = Math.sin(t * 0.65 + obj.phase) * 0.14;
          obj.leftArm.rotation.x = Math.sin(t * 1.8 + obj.phase) * 0.08;
          obj.rightArm.rotation.x = -Math.sin(t * 1.8 + obj.phase) * 0.08;
        }

        obj.ring.scale.setScalar(selectedId === id ? 1.25 + 0.1 * Math.sin(t * 4) : 1.0);

        projVec.set(obj.curX, 1.84 + bob, obj.curZ);
        projVec.project(camera);
        if (projVec.z < 1) {
          const sx = (projVec.x * 0.5 + 0.5) * cw;
          const sy = (-projVec.y * 0.5 + 0.5) * ch;
          obj.tag.style.display = "inline-flex";
          obj.tag.style.left = `${sx}px`;
          obj.tag.style.top = `${sy}px`;
          if ((isWorking || String(obj.task).startsWith("📌")) && obj.task) {
            obj.bubble.style.display = "block";
            obj.bubble.style.left = `${sx}px`;
            obj.bubble.style.top = `${sy - 30}px`;
          }
        } else {
          obj.tag.style.display = "none";
          obj.bubble.style.display = "none";
        }
      }

      wallPins.forEach((wp) => {
        projVec.copy(wp.pos).project(camera);
        if (projVec.z < 1) {
          wp.el.style.display = "inline-block";
          wp.el.style.left = `${(projVec.x * 0.5 + 0.5) * cw}px`;
          wp.el.style.top = `${(-projVec.y * 0.5 + 0.5) * ch}px`;
        } else {
          wp.el.style.display = "none";
        }
      });

      packets.forEach((p) => {
        const speedMul = ceoPulseTimer > 0 && p.fromId === "director" ? 0.68 : 0.28;
        p.t = (p.t + dt * speedMul) % 1;
        const a = agentObjects.get(p.fromId);
        const b = agentObjects.get(p.toId);
        if (a && b) {
          const x = a.curX + (b.curX - a.curX) * p.t;
          const z = a.curZ + (b.curZ - a.curZ) * p.t;
          const y = 1.2 + Math.sin(p.t * Math.PI) * 1.45;
          p.mesh.position.set(x, y, z);
          p.mesh.scale.setScalar(ceoPulseTimer > 0 && p.fromId === "director" ? 1.45 : 1.0);
        }
      });

      renderer.render(scene, camera);
    }

    animate();

    return {
      focusRoom,
      selectAgent,
      setBriefingMode,
      setSearch,
      updateState,
      triggerCeoCommandPulse,
      handleResize,
      destroy: () => {
        if (rafId) cancelAnimationFrame(rafId);
        window.removeEventListener("resize", handleResize);
      },
    };
  }

  function create2DFallbackOffice(canvas, labelsLayer, onSelectAgent) {
    const ctx = canvas.getContext("2d");
    labelsLayer.innerHTML = "";
    function draw() {
      const parent = canvas.parentElement;
      canvas.width = Math.max(parent.clientWidth, 400);
      canvas.height = Math.max(parent.clientHeight, 360);
      ctx.fillStyle = "#081229";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      const cx = canvas.width / 2;
      const cy = canvas.height / 2 + 20;
      AGENT_DEFS.forEach((d, idx) => {
        const ang = (idx / AGENT_DEFS.length) * Math.PI * 2;
        const x = cx + Math.cos(ang) * 170;
        const y = cy + Math.sin(ang) * 95;
        ctx.fillStyle = d.accent;
        ctx.beginPath();
        ctx.arc(x, y, 16, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#f8fafc";
        ctx.font = "bold 12px Inter, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(d.label, x, y + 32);
      });
    }
    draw();
    window.addEventListener("resize", draw);
    return {
      focusRoom: () => {},
      selectAgent: (id) => onSelectAgent(id),
      setBriefingMode: () => {},
      setSearch: () => {},
      updateState: draw,
      triggerCeoCommandPulse: () => {},
      handleResize: draw,
      destroy: () => window.removeEventListener("resize", draw),
    };
  }

  window.XanVirtualOffice3D = { create: createVirtualOffice, AGENT_DEFS };
})();
