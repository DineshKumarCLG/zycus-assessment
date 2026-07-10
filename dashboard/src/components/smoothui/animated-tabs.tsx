"use client";
import { motion } from "framer-motion";
import { useState } from "react";
import { cn } from "@/lib/utils";

interface Tab {
  id: string;
  label: string;
}

interface AnimatedTabsProps {
  tabs: Tab[];
  activeTab: string;
  setActiveTab: (id: string) => void;
  className?: string;
}

export function AnimatedTabs({ tabs, activeTab, setActiveTab, className }: AnimatedTabsProps) {
  return (
    <div className={cn("flex space-x-1 rounded-full bg-zinc-100/50 p-1 backdrop-blur-md border border-zinc-200 shadow-inner w-fit", className)}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => setActiveTab(tab.id)}
          className={cn(
            "relative rounded-full px-5 py-2 text-sm font-medium transition-colors outline-none",
            activeTab === tab.id ? "text-zinc-900" : "text-zinc-500 hover:text-zinc-900"
          )}
        >
          {activeTab === tab.id && (
            <motion.div
              layoutId="active-tab"
              className="absolute inset-0 rounded-full bg-white border border-zinc-200 shadow-sm"
              transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
            />
          )}
          <span className="relative z-10">{tab.label}</span>
        </button>
      ))}
    </div>
  );
}
