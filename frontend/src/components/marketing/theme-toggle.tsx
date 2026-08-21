"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

export function MarketingThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("pdv.theme", next);
    setTheme(next);
  }

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="inline-flex size-10 items-center justify-center rounded-xl border border-subtle bg-surface/90 text-muted shadow-sm transition hover:border-primary/25 hover:text-fg focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20"
      aria-label={theme === "dark" ? "Usar tema claro" : "Usar tema escuro"}
      title={theme === "dark" ? "Usar tema claro" : "Usar tema escuro"}
    >
      {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}
