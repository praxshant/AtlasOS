'use client';

import React, { useRef, useEffect, useState } from 'react';

interface Node {
  id: string;
  name: string;
  label: string;
  confidence: number;
  properties?: any;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}

interface Edge {
  source: string;
  target: string;
  type: string;
  confidence: number;
}

interface GraphViewerProps {
  data: {
    nodes: Node[];
    edges: Edge[];
  };
  onNodeClick?: (node: Node) => void;
}

const LABEL_COLORS: Record<string, string> = {
  Asset: '#0ea5e9',       // Teal
  Incident: '#f97316',    // Coral
  Regulation: '#f59e0b',  // Amber
  Person: '#8b5cf6',      // Purple
  Procedure: '#10b981',   // Green
  FailureMode: '#ef4444', // Red
  Equipment: '#06b6d4',   // Cyan
  LessonLearned: '#ec4899', // Pink
  AuditFinding: '#a855f7' // Violet
};

export default function GraphViewer({ data, onNodeClick }: GraphViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [hoveredNode, setHoveredNode] = useState<Node | null>(null);
  
  // Refs for tracking mutable simulation state
  const nodesRef = useRef<Node[]>([]);
  const edgesRef = useRef<Edge[]>([]);
  const draggingNodeRef = useRef<Node | null>(null);
  const isPanningRef = useRef(false);
  const startPanRef = useRef({ x: 0, y: 0 });
  const startMouseRef = useRef({ x: 0, y: 0 });

  // Sync props data to internal simulation nodes
  useEffect(() => {
    const existingNodes = new Map(nodesRef.current.map(n => [n.id, n]));
    
    // Copy positions for existing nodes, initialize new ones around center
    nodesRef.current = data.nodes.map(n => {
      const existing = existingNodes.get(n.id);
      return {
        ...n,
        x: existing?.x ?? (Math.random() - 0.5) * 200 + 400,
        y: existing?.y ?? (Math.random() - 0.5) * 200 + 300,
        vx: existing?.vx ?? 0,
        vy: existing?.vy ?? 0
      };
    });

    edgesRef.current = data.edges;
  }, [data]);

  // Main Canvas Rendering and Force Simulation Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationId: number;

    const runSimulation = () => {
      const nodes = nodesRef.current;
      const edges = edgesRef.current;

      // 1. Apply Physics Forces
      const width = canvas.width;
      const height = canvas.height;
      const center = { x: width / 2, y: height / 2 };

      // Coulomb Repulsion between all nodes
      for (let i = 0; i < nodes.length; i++) {
        const nodeA = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const nodeB = nodes[j];
          const dx = nodeB.x! - nodeA.x!;
          const dy = nodeB.y! - nodeA.y!;
          const distSq = dx * dx + dy * dy + 0.1;
          const dist = Math.sqrt(distSq);

          if (dist < 220) {
            // Repulsion strength
            const force = 180 / distSq;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;

            nodeA.vx! -= fx;
            nodeA.vy! -= fy;
            nodeB.vx! += fx;
            nodeB.vy! += fy;
          }
        }
      }

      // Spring Attraction along edges (Hooke's Law)
      const nodeMap = new Map(nodes.map(n => [n.id, n]));
      for (const edge of edges) {
        const source = nodeMap.get(edge.source);
        const target = nodeMap.get(edge.target);
        if (source && target) {
          const dx = target.x! - source.x!;
          const dy = target.y! - source.y!;
          const dist = Math.sqrt(dx * dx + dy * dy) || 0.1;
          const desiredDist = 120;
          const k = 0.04; // Spring stiffness
          const force = (dist - desiredDist) * k;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;

          source.vx! += fx;
          source.vy! += fy;
          target.vx! -= fx;
          target.vy! -= fy;
        }
      }

      // Gravity pull to center
      for (const node of nodes) {
        const dx = center.x - node.x!;
        const dy = center.y - node.y!;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.1;
        node.vx! += dx * 0.005;
        node.vy! += dy * 0.005;

        // Friction dampening
        node.vx! *= 0.85;
        node.vy! *= 0.85;

        // Update positions if not being dragged
        if (node !== draggingNodeRef.current) {
          node.x! += node.vx!;
          node.y! += node.vy!;
        }
      }

      // 2. Render Graph
      ctx.clearRect(0, 0, width, height);
      ctx.save();
      ctx.translate(pan.x, pan.y);
      ctx.scale(zoom, zoom);

      // Draw Edges (Relationships)
      for (const edge of edges) {
        const source = nodeMap.get(edge.source);
        const target = nodeMap.get(edge.target);
        if (source && target) {
          const isHovered = hoveredNode?.id === source.id || hoveredNode?.id === target.id;
          ctx.beginPath();
          ctx.moveTo(source.x!, source.y!);
          ctx.lineTo(target.x!, target.y!);
          ctx.strokeStyle = isHovered ? 'rgba(14, 165, 233, 0.6)' : 'rgba(255, 255, 255, 0.08)';
          ctx.lineWidth = isHovered ? 2.5 : 1.2;
          ctx.stroke();

          // Draw Relationship Type Label along edge if hovered or selected
          if (isHovered && zoom > 0.6) {
            const midX = (source.x! + target.x!) / 2;
            const midY = (source.y! + target.y!) / 2;
            ctx.save();
            ctx.fillStyle = 'rgba(15, 23, 42, 0.8)';
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
            ctx.lineWidth = 1;
            ctx.font = '8px var(--font-mono)';
            const textWidth = ctx.measureText(edge.type).width;
            ctx.fillRect(midX - textWidth / 2 - 4, midY - 6, textWidth + 8, 12);
            ctx.strokeRect(midX - textWidth / 2 - 4, midY - 6, textWidth + 8, 12);
            ctx.fillStyle = 'var(--text-secondary)';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(edge.type, midX, midY);
            ctx.restore();
          }
        }
      }

      // Draw Nodes
      for (const node of nodes) {
        const isSelected = selectedNode?.id === node.id;
        const isHovered = hoveredNode?.id === node.id;
        const color = LABEL_COLORS[node.label] || '#94a3b8';

        ctx.beginPath();
        ctx.arc(node.x!, node.y!, isSelected ? 14 : 11, 0, 2 * Math.PI);
        ctx.fillStyle = color;
        ctx.fill();

        // Node Glow Outline on select/hover
        if (isSelected || isHovered) {
          ctx.beginPath();
          ctx.arc(node.x!, node.y!, isSelected ? 18 : 15, 0, 2 * Math.PI);
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.stroke();
        }

        // Draw Node Label Text
        ctx.fillStyle = isSelected ? 'var(--text-primary)' : 'var(--text-secondary)';
        ctx.font = isSelected ? 'bold 11px var(--font-sans)' : '10px var(--font-sans)';
        ctx.textAlign = 'center';
        ctx.fillText(node.name, node.x!, node.y! - 20);
      }

      ctx.restore();
      animationId = requestAnimationFrame(runSimulation);
    };

    animationId = requestAnimationFrame(runSimulation);

    return () => {
      cancelAnimationFrame(animationId);
    };
  }, [zoom, pan, selectedNode, hoveredNode]);

  // Coordinate transformations
  const getCanvasMousePos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top
    };
  };

  const getSimMousePos = (canvasPos: { x: number, y: number }) => {
    return {
      x: (canvasPos.x - pan.x) / zoom,
      y: (canvasPos.y - pan.y) / zoom
    };
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const mousePos = getCanvasMousePos(e);
    const simPos = getSimMousePos(mousePos);

    // Check if clicked a node
    let clickedNode: Node | null = null;
    for (const node of nodesRef.current) {
      const dx = node.x! - simPos.x;
      const dy = node.y! - simPos.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 15) {
        clickedNode = node;
        break;
      }
    }

    if (clickedNode) {
      draggingNodeRef.current = clickedNode;
    } else {
      isPanningRef.current = true;
      startPanRef.current = { ...pan };
      startMouseRef.current = mousePos;
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const mousePos = getCanvasMousePos(e);
    const simPos = getSimMousePos(mousePos);

    if (draggingNodeRef.current) {
      // Update dragged node position directly
      draggingNodeRef.current.x = simPos.x;
      draggingNodeRef.current.y = simPos.y;
    } else if (isPanningRef.current) {
      const dx = mousePos.x - startMouseRef.current.x;
      const dy = mousePos.y - startMouseRef.current.y;
      setPan({
        x: startPanRef.current.x + dx,
        y: startPanRef.current.y + dy
      });
    } else {
      // Check hover
      let hoverNode: Node | null = null;
      for (const node of nodesRef.current) {
        const dx = node.x! - simPos.x;
        const dy = node.y! - simPos.y;
        if (Math.sqrt(dx * dx + dy * dy) < 15) {
          hoverNode = node;
          break;
        }
      }
      setHoveredNode(hoverNode);
    }
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const mousePos = getCanvasMousePos(e);
    const simPos = getSimMousePos(mousePos);

    if (draggingNodeRef.current) {
      // Trigger node selection if drag was minimal
      const node = draggingNodeRef.current;
      setSelectedNode(node);
      if (onNodeClick) onNodeClick(node);
      draggingNodeRef.current = null;
    }
    
    isPanningRef.current = false;
  };

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const zoomFactor = 1.1;
    let newZoom = zoom;
    if (e.deltaY < 0) {
      newZoom = Math.min(zoom * zoomFactor, 3);
    } else {
      newZoom = Math.max(zoom / zoomFactor, 0.3);
    }
    setZoom(newZoom);
  };

  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });

  useEffect(() => {
    if (!containerRef.current) return;
    const resizeObserver = new ResizeObserver(entries => {
      for (let entry of entries) {
        setDimensions({
          width: entry.contentRect.width,
          height: entry.contentRect.height
        });
      }
    });
    resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, []);

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '100%', height: '100%', minHeight: '400px' }}>
      <canvas
        ref={canvasRef}
        width={dimensions.width}
        height={dimensions.height}
        style={{ 
          width: '100%', 
          height: '100%', 
          background: 'rgba(15, 23, 42, 0.25)', 
          borderRadius: '12px',
          border: '1px solid var(--card-border)',
          cursor: draggingNodeRef.current ? 'grabbing' : hoveredNode ? 'grab' : isPanningRef.current ? 'grabbing' : 'move'
        }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onWheel={handleWheel}
      />
      <div 
        style={{ 
          position: 'absolute', 
          bottom: '1rem', 
          right: '1rem', 
          background: 'rgba(15, 23, 42, 0.85)', 
          border: '1px solid var(--card-border)',
          padding: '0.5rem 0.75rem',
          borderRadius: '6px',
          fontSize: '0.75rem',
          color: 'var(--text-secondary)',
          display: 'flex',
          gap: '0.75rem',
          backdropFilter: 'blur(5px)'
        }}
      >
        <span>Zoom: {Math.round(zoom * 100)}%</span>
        <span>•</span>
        <span>Drag node to move</span>
        <span>•</span>
        <span>Scroll to zoom</span>
        <span>•</span>
        <button 
          onClick={() => { setPan({x:0, y:0}); setZoom(1); }} 
          style={{ background: 'transparent', border: 'none', color: 'var(--accent-teal)', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}
        >
          Reset View
        </button>
      </div>
    </div>
  );
}
