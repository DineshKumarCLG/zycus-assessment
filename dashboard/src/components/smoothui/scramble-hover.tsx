"use client";
import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";

interface ScrambleHoverProps {
  text: string;
  className?: string;
  scrambleSpeed?: number;
}

const CHARS = "!<>-_\\\\/[]{}—=+*^?#________";

export function ScrambleHover({ text, className, scrambleSpeed = 50 }: ScrambleHoverProps) {
  const [displayText, setDisplayText] = useState(text);
  const [isHovering, setIsHovering] = useState(false);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isHovering) {
      let iteration = 0;
      interval = setInterval(() => {
        setDisplayText((prev) =>
          prev
            .split("")
            .map((letter, index) => {
              if (index < iteration) return text[index];
              return CHARS[Math.floor(Math.random() * CHARS.length)];
            })
            .join("")
        );

        if (iteration >= text.length) {
          clearInterval(interval);
        }
        iteration += 1 / 3;
      }, scrambleSpeed);
    } else {
      setDisplayText(text);
    }
    return () => clearInterval(interval);
  }, [isHovering, text, scrambleSpeed]);

  return (
    <span
      className={cn("inline-block font-mono cursor-default", className)}
      onMouseEnter={() => setIsHovering(true)}
      onMouseLeave={() => setIsHovering(false)}
    >
      {displayText}
    </span>
  );
}
