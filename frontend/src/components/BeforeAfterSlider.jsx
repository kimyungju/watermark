import { useState, useEffect, useRef, useCallback } from "react";

export default function BeforeAfterSlider({ beforeSrc, afterSrc }) {
  const [position, setPosition] = useState(50);
  const [loaded, setLoaded] = useState(false);
  const containerRef = useRef(null);
  const dragging = useRef(false);

  // Reset loaded state when images change (page navigation)
  useEffect(() => {
    setLoaded(false);
  }, [beforeSrc, afterSrc]);

  const updatePosition = useCallback((clientX) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = Math.max(0, Math.min(clientX - rect.left, rect.width));
    setPosition((x / rect.width) * 100);
  }, []);

  const handleMouseDown = (e) => {
    e.preventDefault();
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
      className="group relative cursor-col-resize select-none overflow-hidden rounded-xl"
      style={{ border: "1px solid var(--color-border)" }}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onTouchMove={handleTouchMove}
    >
      {/* After image (full, bottom layer) */}
      <img
        src={afterSrc}
        alt="After"
        className="block w-full"
        draggable={false}
        onLoad={() => setLoaded(true)}
      />

      {/* Before image (clipped) */}
      <img
        src={beforeSrc}
        alt="Before"
        className="absolute top-0 left-0 block w-full"
        style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}
        draggable={false}
      />

      {/* Divider line with glow */}
      <div
        className="slider-glow pointer-events-none absolute top-0 bottom-0 w-[2px] bg-[var(--color-accent)]"
        style={{
          left: `${position}%`,
          transform: "translateX(-50%)",
        }}
      />

      {/* Slider handle */}
      <div
        className="absolute top-0 bottom-0 z-10 w-10 cursor-col-resize"
        style={{
          left: `${position}%`,
          transform: "translateX(-50%)",
        }}
        onMouseDown={handleMouseDown}
        onTouchStart={handleMouseDown}
      >
        <div
          className="absolute top-1/2 left-1/2 flex h-9 w-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full transition-transform duration-150 group-hover:scale-110"
          style={{
            background: "var(--color-accent)",
            boxShadow:
              "0 0 0 3px var(--color-base), 0 2px 12px var(--color-accent-glow)",
          }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill="none"
            stroke="var(--color-base)"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <path d="M5 4L2 8l3 4" />
            <path d="M11 4l3 4-3 4" />
          </svg>
        </div>
      </div>

      {/* Labels */}
      {loaded && (
        <>
          <div
            className="animate-fade-in absolute top-3 left-3 rounded-md px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider"
            style={{
              background: "rgba(0, 0, 0, 0.65)",
              backdropFilter: "blur(8px)",
              color: "var(--color-text-muted)",
            }}
          >
            Before
          </div>
          <div
            className="animate-fade-in absolute top-3 right-3 rounded-md px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider"
            style={{
              background: "rgba(0, 0, 0, 0.65)",
              backdropFilter: "blur(8px)",
              color: "var(--color-text-muted)",
            }}
          >
            After
          </div>
        </>
      )}
    </div>
  );
}
