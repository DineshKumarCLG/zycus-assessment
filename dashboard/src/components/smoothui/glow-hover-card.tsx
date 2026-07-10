"use client";
import React, { useRef, useState, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface GlowHoverCardProps {
  children: ReactNode;
  className?: string;
  glowColor?: string;
}

export function GlowHoverCard({ children, className, glowColor = "rgba(255, 255, 255, 0.15)" }: GlowHoverCardProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [opacity, setOpacity] = useState(0);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    setPosition({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
  };

  const handleMouseEnter = () => setOpacity(1);
  const handleMouseLeave = () => setOpacity(0);

  return (
    <div
      ref={containerRef}
      onMouseMove={handleMouseMove}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className={cn(
        "relative flex flex-col items-start overflow-hidden rounded-3xl border border-zinc-200 bg-white text-zinc-900 shadow-sm transition-colors hover:border-zinc-300",
        className
      )}
    >
      <div
        className="pointer-events-none absolute -inset-px opacity-0 transition duration-300"
        style={{
          opacity,
          background: `radial-gradient(600px circle at ${position.x}px ${position.y}px, ${glowColor}, transparent 40%)`,
        }}
      />
      <div className="z-10 w-full p-6">{children}</div>
    </div>
  );
}
