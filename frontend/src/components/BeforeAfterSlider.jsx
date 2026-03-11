import { useState, useEffect, useRef, useCallback } from "react";

export default function BeforeAfterSlider({ beforeSrc, afterSrc }) {
  const [position, setPosition] = useState(50);
  const [containerWidth, setContainerWidth] = useState(0);
  const containerRef = useRef(null);
  const dragging = useRef(false);

  // Track container width for before image sizing
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      setContainerWidth(entries[0].contentRect.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const updatePosition = useCallback((clientX) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = Math.max(0, Math.min(clientX - rect.left, rect.width));
    setPosition((x / rect.width) * 100);
  }, []);

  const handleMouseDown = () => {
    dragging.current = true;
  };

  const handleMouseMove = useCallback(
    (e) => {
      if (dragging.current) {
        updatePosition(e.clientX);
      }
    },
    [updatePosition]
  );

  const handleMouseUp = () => {
    dragging.current = false;
  };

  const handleTouchMove = useCallback(
    (e) => {
      updatePosition(e.touches[0].clientX);
    },
    [updatePosition]
  );

  return (
    <div
      ref={containerRef}
      className="relative cursor-col-resize select-none overflow-hidden rounded-lg"
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onTouchMove={handleTouchMove}
    >
      {/* After image (full width, bottom layer) */}
      <img src={afterSrc} alt="After" className="block w-full" draggable={false} />

      {/* Before image (clipped) */}
      <div
        className="absolute inset-0 overflow-hidden"
        style={{ width: `${position}%` }}
      >
        <img
          src={beforeSrc}
          alt="Before"
          className="block w-full"
          style={{ width: `${containerWidth}px` }}
          draggable={false}
        />
      </div>

      {/* Slider handle */}
      <div
        className="absolute top-0 bottom-0 w-1 cursor-col-resize bg-white shadow-lg"
        style={{ left: `${position}%`, transform: "translateX(-50%)" }}
        onMouseDown={handleMouseDown}
        onTouchStart={handleMouseDown}
      >
        <div className="absolute top-1/2 left-1/2 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white shadow-lg">
          <span className="text-xs text-gray-800">{"\u27F7"}</span>
        </div>
      </div>

      {/* Labels */}
      <div className="absolute top-2 left-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">
        Before
      </div>
      <div className="absolute top-2 right-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">
        After
      </div>
    </div>
  );
}
