/**
 * The knowledge graph canvas: 3D (three.js via `3d-force-graph`) or 2D (`force-graph`).
 *
 * The vanilla libraries, wrapped in one component, rather than `react-force-graph-3d`: no React 19
 * peer dependency to fight, and one place owns the WebGL lifecycle (ADR-011). This component only
 * draws. What is visible, what is lit and what a click means are decided by `model.ts` and the
 * explorer; this turns those decisions into pixels and reports the user's gestures back.
 *
 * Nothing relies on colour alone: each kind of node has its own shape (`shapeOf`), and a
 * contradiction's link is labelled and carries moving particles as well as being red.
 */

import ForceGraph3D from "3d-force-graph";
import type { ConfigOptions, ForceGraph3DInstance } from "3d-force-graph";
import ForceGraph from "force-graph";
import { useEffect, useRef } from "react";
import * as THREE from "three";
import SpriteText from "three-spritetext";

import type { GraphLinkKind, GraphNode } from "../../api/types";
import type { VisibleGraph } from "./model";
import { colourOf, linkColourOf, linkKey, particlesOf, shapeOf, shortLabel, sizeOf } from "./model";

/** A node as the libraries hold it: the API node plus the layout's coordinates. */
type DrawnNode = GraphNode & { x?: number; y?: number; z?: number };
type DrawnLink = {
  source: string | DrawnNode;
  target: string | DrawnNode;
  kind: GraphLinkKind;
  label: string;
};

export interface GraphCanvasProps {
  graph: VisibleGraph;
  /** Lit node ids; null when nothing is selected, so nothing is dimmed. */
  lit: ReadonlySet<string> | null;
  litLinks: ReadonlySet<string> | null;
  selectedId: string | null;
  /** Fly the camera here when it changes. */
  focusId: string | null;
  mode: "2d" | "3d";
  onHover: (node: GraphNode | null, x: number, y: number) => void;
  onClick: (node: GraphNode) => void;
  onDoubleClick: (node: GraphNode) => void;
  onBackground: () => void;
}

const BACKGROUND = "#0b0e14";
const DIM = 0.12;
const DOUBLE_CLICK_MS = 350;
// Lay out part of the graph before the first frame, and let it settle within a second or two
// rather than the library's 15 s default, so the view frames itself promptly.
const WARMUP_TICKS = 40;
const COOLDOWN_TICKS = 120;
// A run's graph is mostly loose entities with few links; at the library's default repulsion (-30)
// they drift far apart and the labels become unreadable once framed (screenshot 4, 2026-10-04).
const CHARGE = -12;
const LABEL_HEIGHT = 5;
// Sub-node labels are smaller: an entity's claims crowd its neighbourhood once it is lit
// (3D click screenshot, 2026-10-04). Their full text is in the side panel.
const SUB_LABEL_HEIGHT = 2.6;
// How far from a node the camera stops when it flies there.
const FLY_DISTANCE = 150;
const FLY_RETRIES = 10;
const FLY_RETRY_MS = 150;
// Re-frame the graph at these delays after new data, until the engine reports it has stopped:
// the stop event can arrive late or never when the tab is throttled, and one early fit frames
// a layout that has not spread out yet (screenshots 5 and 6, 2026-10-04).
const FIT_FALLBACK_MS = [1200, 3000, 6000];

type Graph2D = ForceGraph<DrawnNode, DrawnLink>;
type Graph3D = ForceGraph3DInstance<DrawnNode, DrawnLink>;
// The library types its constructor as a generic interface that `new` cannot parameterise
// directly; this gives it the node and link types once, so every accessor below is typed.
const Graph3DCtor = ForceGraph3D as unknown as new (
  element: HTMLElement,
  config?: ConfigOptions,
) => Graph3D;

export function KnowledgeGraph3D(props: GraphCanvasProps) {
  const container = useRef<HTMLDivElement | null>(null);
  const graph3d = useRef<Graph3D | null>(null);
  const graph2d = useRef<Graph2D | null>(null);
  // Live values the libraries' accessors read on every frame, without rebuilding the instance.
  const live = useRef(props);
  live.current = props;
  const nodes = useRef(new Map<string, DrawnNode>());
  const pointer = useRef({ x: 0, y: 0 });
  const lastClick = useRef({ id: "", at: 0 });
  const pendingFit = useRef(true);

  // --- one instance per mode ---------------------------------------------------------------
  useEffect(() => {
    const element = container.current;
    if (!element) return;

    const isLit = (id: string) => !live.current.lit || live.current.lit.has(id);
    const linkLit = (l: DrawnLink) =>
      !live.current.litLinks || live.current.litLinks.has(linkKey(plainLink(l)));
    const handleClick = (node: DrawnNode) => {
      const now = performance.now();
      if (lastClick.current.id === node.id && now - lastClick.current.at < DOUBLE_CLICK_MS) {
        live.current.onDoubleClick(node);
        lastClick.current = { id: "", at: 0 };
        return;
      }
      lastClick.current = { id: node.id, at: now };
      live.current.onClick(node);
    };
    const handleHover = (node: DrawnNode | null) =>
      live.current.onHover(node, pointer.current.x, pointer.current.y);
    const linkLabel = (l: DrawnLink) =>
      l.kind === "CONFLICTS_WITH" ? `conflicts: ${l.label}` : l.label || l.kind.toLowerCase();

    if (live.current.mode === "3d") {
      const instance = new Graph3DCtor(element, { controlType: "orbit" })
        .backgroundColor(BACKGROUND)
        .showNavInfo(false)
        .warmupTicks(WARMUP_TICKS)
        .cooldownTicks(COOLDOWN_TICKS)
        .nodeLabel(() => "")
        .nodeThreeObject((node) => {
          const object = buildNode(node);
          styleNode(object, node, isLit(node.id), node.id === live.current.selectedId, !!live.current.lit);
          return object;
        })
        .linkColor((l) => (linkLit(l) ? linkColourOf(l.kind) : "rgba(51,61,82,0.15)"))
        .linkWidth((l) => (l.kind === "CONFLICTS_WITH" ? 1.6 : linkLit(l) ? 0.8 : 0.3))
        .linkOpacity(0.7)
        .linkLabel(linkLabel)
        .linkDirectionalParticles((l) => (linkLit(l) ? particlesOf(l.kind) : 0))
        .linkDirectionalParticleWidth(2.4)
        .linkDirectionalParticleColor(() => "#f0616d")
        .onNodeHover(handleHover)
        .onNodeClick(handleClick)
        .onBackgroundClick(() => live.current.onBackground());
      tighten(instance.d3Force("charge"));
      graph3d.current = instance;
    } else {
      const instance = new ForceGraph<DrawnNode, DrawnLink>(element)
        .backgroundColor(BACKGROUND)
        .autoPauseRedraw(false)
        .warmupTicks(WARMUP_TICKS)
        .cooldownTicks(COOLDOWN_TICKS)
        .nodeLabel(() => "")
        .nodeCanvasObject((node, ctx, scale) =>
          draw2d(node, ctx, scale, isLit(node.id), node.id === live.current.selectedId, !!live.current.lit),
        )
        .nodePointerAreaPaint((node, colour, ctx) => {
          ctx.fillStyle = colour;
          ctx.beginPath();
          ctx.arc(node.x ?? 0, node.y ?? 0, sizeOf(node) + 2, 0, 2 * Math.PI);
          ctx.fill();
        })
        .linkColor((l) => (linkLit(l) ? linkColourOf(l.kind) : "rgba(51,61,82,0.2)"))
        .linkWidth((l) => (l.kind === "CONFLICTS_WITH" ? 2 : 1))
        .linkLabel(linkLabel)
        .linkDirectionalParticles((l) => (linkLit(l) ? particlesOf(l.kind) : 0))
        .linkDirectionalParticleWidth(3)
        .linkDirectionalParticleColor(() => "#f0616d")
        .onNodeHover(handleHover)
        .onNodeClick(handleClick)
        .onBackgroundClick(() => live.current.onBackground());
      tighten(instance.d3Force("charge"));
      graph2d.current = instance;
    }

    // Size the canvas to its container now, not on the first ResizeObserver callback: until then
    // the library uses the window's size, and the graph is drawn off-centre (seen in the first
    // screenshot of this view, 2026-10-04).
    const fit = () => {
      const { width, height } = element.getBoundingClientRect();
      graph3d.current?.width(width).height(height);
      graph2d.current?.width(width).height(height);
    };
    fit();
    const resize = new ResizeObserver(fit);
    resize.observe(element);
    // Frame the whole graph once the layout settles after new data, unless the user has already
    // flown somewhere.
    const frame = () => {
      if (!pendingFit.current) return;
      pendingFit.current = false;
      frameAll(graph3d.current, graph2d.current, [...nodes.current.values()]);
    };
    graph3d.current?.onEngineStop(frame);
    graph2d.current?.onEngineStop(frame);
    const track = (event: MouseEvent) => {
      const box = element.getBoundingClientRect();
      pointer.current = { x: event.clientX - box.left, y: event.clientY - box.top };
    };
    element.addEventListener("mousemove", track);

    return () => {
      resize.disconnect();
      element.removeEventListener("mousemove", track);
      graph3d.current?._destructor();
      graph2d.current?._destructor();
      graph3d.current = null;
      graph2d.current = null;
      element.replaceChildren();
    };
  }, [props.mode]);

  // --- data: keep each node's object so the layout does not jump when the graph changes --------
  useEffect(() => {
    const kept = new Map<string, DrawnNode>();
    const drawn = props.graph.nodes.map((node) => {
      const existing = nodes.current.get(node.id);
      const next = existing ? Object.assign(existing, node) : { ...node };
      kept.set(node.id, next);
      return next;
    });
    nodes.current = kept;
    if (!live.current.focusId) pendingFit.current = true;
    const links: DrawnLink[] = props.graph.links.map((l) => ({ ...l }));
    graph3d.current?.graphData({ nodes: drawn, links });
    graph2d.current?.graphData({ nodes: drawn, links });
    const timers = FIT_FALLBACK_MS.map((delay) =>
      window.setTimeout(() => {
        if (pendingFit.current) frameAll(graph3d.current, graph2d.current, [...nodes.current.values()]);
      }, delay),
    );
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [props.graph, props.mode]);

  // --- highlight: redraw with the new lit set -------------------------------------------------
  useEffect(() => {
    const instance = graph3d.current;
    if (instance) {
      // Restyle each node's existing object in place; links are cheap, so their accessors are
      // re-set, which makes the library re-evaluate them against `live`.
      const lit = props.lit;
      for (const node of nodes.current.values()) {
        const object = (node as DrawnNode & { __threeObj?: THREE.Object3D }).__threeObj;
        if (object?.userData && "shape" in object.userData) {
          styleNode(object, node, !lit || lit.has(node.id), node.id === props.selectedId, !!lit);
        }
      }
      instance.linkColor(instance.linkColor());
      instance.linkWidth(instance.linkWidth());
      instance.linkDirectionalParticles(instance.linkDirectionalParticles());
    }
  }, [props.lit, props.litLinks, props.selectedId]);

  // --- fly to the focused node ------------------------------------------------------------------
  // A node the same click added (a finding opened by its trail, a claim just unfolded) has no
  // position until the layout ticks, so wait for one. The camera approaches along its current line
  // of sight: the first version moved out from the origin, which put it inside the graph when the
  // target sat at or had not yet left the origin (trail screenshot, 2026-10-04).
  useEffect(() => {
    const id = props.focusId;
    if (!id) return;
    pendingFit.current = false;
    let timer = 0;
    const fly = (attempt: number) => {
      const target = nodes.current.get(id);
      if (!target) return;
      if (target.x === undefined || target.y === undefined) {
        if (attempt < FLY_RETRIES) timer = window.setTimeout(() => fly(attempt + 1), FLY_RETRY_MS);
        return;
      }
      const { x, y, z = 0 } = target;
      if (graph3d.current) {
        const from = graph3d.current.cameraPosition();
        const dx = from.x - x;
        const dy = from.y - y;
        const dz = from.z - z;
        const length = Math.hypot(dx, dy, dz) || 1;
        const scale = FLY_DISTANCE / length;
        graph3d.current.cameraPosition(
          { x: x + dx * scale, y: y + dy * scale, z: z + (length > 1 ? dz * scale : FLY_DISTANCE) },
          { x, y, z },
          900,
        );
      }
      if (graph2d.current) {
        graph2d.current.centerAt(x, y, 700);
        graph2d.current.zoom(3, 700);
      }
    };
    fly(0);
    return () => window.clearTimeout(timer);
  }, [props.focusId]);

  return <div ref={container} className="graph-canvas" aria-hidden="true" />;
}

/**
 * Frame every node. In 3D the camera is placed from the nodes themselves (their centre, and the
 * farthest node against the narrower half of the field of view) rather than with the library's
 * `zoomToFit`, which framed this view far too close in testing (screenshots 6 and 7, 2026-10-04).
 */
function frameAll(g3: Graph3D | null, g2: Graph2D | null, all: DrawnNode[]): void {
  g2?.zoomToFit(600, 40);
  if (!g3 || all.length === 0) return;
  const n = all.length;
  const c = all.reduce(
    (sum, node) => ({ x: sum.x + (node.x ?? 0) / n, y: sum.y + (node.y ?? 0) / n, z: sum.z + (node.z ?? 0) / n }),
    { x: 0, y: 0, z: 0 },
  );
  const radius = Math.max(
    10,
    ...all.map((node) => Math.hypot((node.x ?? 0) - c.x, (node.y ?? 0) - c.y, (node.z ?? 0) - c.z) + sizeOf(node)),
  );
  const camera = g3.camera() as THREE.PerspectiveCamera;
  const vertical = (camera.fov * Math.PI) / 360;
  const horizontal = Math.atan(Math.tan(vertical) * camera.aspect);
  const distance = (radius / Math.sin(Math.min(vertical, horizontal))) * 1.05;
  g3.cameraPosition({ x: c.x, y: c.y, z: c.z + distance }, c, 600);
}

/** Weaken the many-body repulsion; the force is d3's, typed loosely by the libraries. */
function tighten(force: unknown): void {
  (force as { strength?: (value: number) => unknown } | undefined)?.strength?.(CHARGE);
}

function plainLink(l: DrawnLink): { source: string; target: string; kind: GraphLinkKind } {
  const id = (end: string | DrawnNode) => (typeof end === "string" ? end : end.id);
  return { source: id(l.source), target: id(l.target), kind: l.kind };
}

/** What a node's 3D object holds, so a highlight change can restyle it without rebuilding it. */
interface NodeParts {
  shape: THREE.Mesh<THREE.BufferGeometry, THREE.MeshLambertMaterial>;
  label: SpriteText;
}

/**
 * Build a node's 3D object once: its shape, and a label that is always present but shown only when
 * the labelling rule says so. Rebuilding every mesh and label texture on each click made a click
 * cost a full scene rebuild, which froze the page under software WebGL (2026-10-04).
 */
function buildNode(node: DrawnNode): THREE.Object3D {
  const radius = sizeOf(node) * 0.7;
  const geometry = {
    sphere: () => new THREE.SphereGeometry(radius, 16, 12),
    cube: () => new THREE.BoxGeometry(radius * 1.4, radius * 1.4, radius * 1.4),
    octahedron: () => new THREE.OctahedronGeometry(radius * 1.2),
    tetrahedron: () => new THREE.TetrahedronGeometry(radius * 1.4),
  }[shapeOf(node.kind)]();
  const shape = new THREE.Mesh(geometry, new THREE.MeshLambertMaterial({ transparent: true }));
  const height = node.kind === "ENTITY" ? LABEL_HEIGHT : SUB_LABEL_HEIGHT;
  const label = new SpriteText(shortLabel(node.label), height, "#e3e8f0");
  label.material.transparent = true;
  label.position.y = -(radius + height);
  const group = new THREE.Group();
  group.add(shape, label);
  const parts: NodeParts = { shape, label };
  group.userData = parts;
  return group;
}

/** Apply the current highlight to a node's object, in place. */
function styleNode(object: THREE.Object3D, node: DrawnNode, lit: boolean, selected: boolean, anySelection: boolean): void {
  const { shape, label } = object.userData as NodeParts;
  shape.material.color.set(colourOf(node));
  shape.material.opacity = lit ? 0.95 : DIM;
  shape.material.emissive.set(selected ? "#ffffff" : "#000000");
  shape.material.emissiveIntensity = selected ? 0.35 : 0;
  // The same labelling rule as 2D: entities always, anything lit once something is selected.
  label.visible = node.kind === "ENTITY" || (anySelection && lit);
  label.material.opacity = lit ? 1 : 0.15;
}

function draw2d(
  node: DrawnNode,
  ctx: CanvasRenderingContext2D,
  scale: number,
  lit: boolean,
  selected: boolean,
  anySelection: boolean,
): void {
  const x = node.x ?? 0;
  const y = node.y ?? 0;
  const r = sizeOf(node);
  ctx.globalAlpha = lit ? 1 : DIM;
  ctx.fillStyle = colourOf(node);
  ctx.beginPath();
  switch (shapeOf(node.kind)) {
    case "sphere":
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      break;
    case "cube":
      ctx.rect(x - r, y - r, 2 * r, 2 * r);
      break;
    case "octahedron":
      ctx.moveTo(x, y - r * 1.3);
      ctx.lineTo(x + r * 1.3, y);
      ctx.lineTo(x, y + r * 1.3);
      ctx.lineTo(x - r * 1.3, y);
      ctx.closePath();
      break;
    case "tetrahedron":
      ctx.moveTo(x, y - r * 1.4);
      ctx.lineTo(x + r * 1.3, y + r);
      ctx.lineTo(x - r * 1.3, y + r);
      ctx.closePath();
      break;
  }
  ctx.fill();
  if (selected) {
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.5 / scale;
    ctx.stroke();
  }
  // Labels for entities always, and for anything lit once something is selected.
  if (node.kind === "ENTITY" || (anySelection && lit)) {
    ctx.font = `${12 / scale}px sans-serif`;
    ctx.fillStyle = "#e3e8f0";
    ctx.textAlign = "center";
    ctx.fillText(shortLabel(node.label), x, y + r + 12 / scale);
  }
  ctx.globalAlpha = 1;
}
