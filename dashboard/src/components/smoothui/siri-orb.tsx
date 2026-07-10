"use client";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface SiriOrbProps {
  color?: "green" | "amber" | "red";
  className?: string;
  size?: number;
}

export function SiriOrb({ color = "green", className, size = 64 }: SiriOrbProps) {
  const colorMap = {
    green: "from-emerald-400 via-emerald-600 to-emerald-900",
    amber: "from-amber-400 via-amber-600 to-amber-900",
    red: "from-rose-400 via-rose-600 to-rose-900",
  };

  const shadowMap = {
    green: "0 0 40px rgba(16, 185, 129, 0.4)",
    amber: "0 0 40px rgba(245, 158, 11, 0.4)",
    red: "0 0 40px rgba(225, 29, 72, 0.4)",
  };

  return (
    <div
      className={cn("relative flex items-center justify-center rounded-full", className)}
      style={{ width: size, height: size }}
    >
      <motion.div
        animate={{
          scale: [1, 1.1, 1],
          rotate: [0, 90, 180, 270, 360],
          filter: ["blur(8px)", "blur(12px)", "blur(8px)"],
        }}
        transition={{
          duration: 4,
          repeat: Infinity,
          ease: "linear",
        }}
        className={cn(
          "absolute inset-0 rounded-full bg-gradient-to-tr opacity-80 mix-blend-screen",
          colorMap[color]
        )}
        style={{ boxShadow: shadowMap[color] }}
      />
      <motion.div
        animate={{
          scale: [0.9, 1.2, 0.9],
          rotate: [360, 270, 180, 90, 0],
        }}
        transition={{
          duration: 5,
          repeat: Infinity,
          ease: "linear",
        }}
        className={cn(
          "absolute inset-2 rounded-full bg-gradient-to-bl opacity-60 mix-blend-screen",
          colorMap[color]
        )}
      />
      <div className="absolute inset-0 rounded-full border border-white/20 shadow-inner" />
    </div>
  );
}
