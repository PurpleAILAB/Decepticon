"use client";

/**
 * useCanvasTransform — pan & zoom for the SVG agent graph canvas.
 *
 * Manages a 2D affine transform (translate + uniform scale) driven by
 * mouse drag (pan) and mouse wheel (zoom). Provides a fitToViewport
 * helper that frames all nodes with padding.
 */

import { useCallback, useEffect, useRef, useState } from "react";

const MIN_SCALE = 0.3;
const MAX_SCALE = 3.0;
const ZOOM_FACTOR = 0.1;
const FIT_PADDING = 80;

export interface CanvasTransform {
  tx: number;
  ty: number;
  scale: number;
}

interface UseCanvasTransformReturn {
  transform: CanvasTransform;
  /** SVG transform attribute string. */
  transformAttr: string;
  /** Attach to SVG onWheel. */
  onWheel: (e: React.WheelEvent) => void;
  /** Attach to SVG onMouseDown for pan start. */
  onMouseDown: (e: React.MouseEvent) => void;
  /** Attach to window onMouseMove for panning. */
  onMouseMove: (e: React.MouseEvent | MouseEvent) => void;
  /** Attach to window onMouseUp for pan end. */
  onMouseUp: () => void;
  /** Whether the user is currently panning. */
  isPanning: boolean;
  /** Fit all nodes into the viewport. */
  fitToViewport: (
    nodePositions: Array<{ x: number; y: number }>,
    containerWidth: number,
    containerHeight: number,
  ) => void;
  /** Convert screen coordinates to graph coordinates. */
  screenToGraph: (sx: number, sy: number) => { x: number; y: number };
}

export function useCanvasTransform(): UseCanvasTransformReturn {
  const [transform, setTransform] = useState<CanvasTransform>({
    tx: 0,
    ty: 0,
    scale: 1,
  });

  const panStart = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);
  const [isPanning, setIsPanning] = useState(false);

  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const target = e.currentTarget as SVGSVGElement | null;
    if (!target) return;
    const direction = e.deltaY < 0 ? 1 : -1;
    const rect = target.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;

    setTransform((prev) => {
      const newScale = Math.min(
        MAX_SCALE,
        Math.max(MIN_SCALE, prev.scale + direction * ZOOM_FACTOR),
      );

      const scaleFactor = newScale / prev.scale;
      const newTx = cx - scaleFactor * (cx - prev.tx);
      const newTy = cy - scaleFactor * (cy - prev.ty);

      return { tx: newTx, ty: newTy, scale: newScale };
    });
  }, []);

  const transformRef = useRef(transform);
  useEffect(() => { transformRef.current = transform; }, [transform]);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    panStart.current = {
      x: e.clientX,
      y: e.clientY,
      tx: transformRef.current.tx,
      ty: transformRef.current.ty,
    };
    setIsPanning(true);
  }, []);

  const onMouseMove = useCallback((e: React.MouseEvent | MouseEvent) => {
    const start = panStart.current;
    if (!start) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    setTransform((prev) => ({
      ...prev,
      tx: start.tx + dx,
      ty: start.ty + dy,
    }));
  }, []);

  const onMouseUp = useCallback(() => {
    panStart.current = null;
    setIsPanning(false);
  }, []);

  const fitToViewport = useCallback(
    (
      nodePositions: Array<{ x: number; y: number }>,
      containerWidth: number,
      containerHeight: number,
    ) => {
      if (nodePositions.length === 0) {
        setTransform({ tx: containerWidth / 2, ty: containerHeight / 2, scale: 1 });
        return;
      }

      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      for (const { x, y } of nodePositions) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }

      const graphW = maxX - minX + FIT_PADDING * 2;
      const graphH = maxY - minY + FIT_PADDING * 2;
      const scale = Math.min(
        MAX_SCALE,
        Math.max(MIN_SCALE, Math.min(containerWidth / graphW, containerHeight / graphH)),
      );

      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;
      const tx = containerWidth / 2 - centerX * scale;
      const ty = containerHeight / 2 - centerY * scale;

      setTransform({ tx, ty, scale });
    },
    [],
  );

  const screenToGraph = useCallback(
    (sx: number, sy: number) => ({
      x: (sx - transform.tx) / transform.scale,
      y: (sy - transform.ty) / transform.scale,
    }),
    [transform],
  );

  const transformAttr = `translate(${transform.tx}, ${transform.ty}) scale(${transform.scale})`;

  return {
    transform,
    transformAttr,
    onWheel,
    onMouseDown,
    onMouseMove,
    onMouseUp,
    isPanning,
    fitToViewport,
    screenToGraph,
  };
}
