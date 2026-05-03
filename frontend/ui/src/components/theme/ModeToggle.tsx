"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

// Cycles light → dark → system → light. Single-button variant of the shadcn
// mode toggle — avoids pulling in @radix-ui/react-dropdown-menu for what is
// otherwise a 3-state toggle. Mirrors shadcn's own next-themes integration:
// `attribute="class"` on `<html>`, `enableSystem` for OS preference.
export function ModeToggle() {
  const { resolvedTheme, theme, setTheme } = useTheme();
  // next-themes returns undefined on the server; render a placeholder of the
  // same size to keep the layout stable until hydration resolves.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const next = theme === "system" ? "light" : theme === "light" ? "dark" : "system";
  const cycle = () => setTheme(next);

  if (!mounted) {
    return (
      <Button variant="ghost" size="icon" aria-label="Toggle theme" disabled>
        <Sun className="opacity-0" />
      </Button>
    );
  }

  const Icon = theme === "system" ? Monitor : resolvedTheme === "dark" ? Moon : Sun;
  const label =
    theme === "system"
      ? "Theme: system (click for light)"
      : theme === "light"
        ? "Theme: light (click for dark)"
        : "Theme: dark (click for system)";

  return (
    <Button variant="ghost" size="icon" onClick={cycle} aria-label={label} title={label}>
      <Icon />
    </Button>
  );
}
