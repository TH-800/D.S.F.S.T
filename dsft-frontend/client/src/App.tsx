// App.tsx - the main entry point that sets up routing, sidebar, and providers
// we use hash-based routing so the app works properly when deployed
// dark mode is on by default since this is a monitoring/ops tool

import { Switch, Route, Router } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/Sidebar";
import { AppProvider } from "@/lib/store";
import { useState, useEffect } from "react";
import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";

// page imports
import Dashboard from "@/pages/Dashboard";
import Experiments from "@/pages/Experiments";
import Logs from "@/pages/Logs";
import Reports from "@/pages/Reports";
import NotFound from "@/pages/not-found";

// sets up all the routes for the app
function AppRouter() {
  return (
    <Switch>
      <Route path="/" component={Dashboard} />
      <Route path="/experiments" component={Experiments} />
      <Route path="/logs" component={Logs} />
      <Route path="/reports" component={Reports} />
      {/* if nothing matches show the 404 page */}
      <Route component={NotFound} />
    </Switch>
  );
}

// simple dark/light mode toggle button
function ThemeToggle() {
  const [isDark, setIsDark] = useState(true);

  // on first load, set dark mode (we default to dark for ops tools)
  useEffect(() => {
    document.documentElement.classList.add("dark");
  }, []);

  function toggleTheme() {
    const next = !isDark;
    setIsDark(next);
    if (next) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggleTheme}
      data-testid="button-theme-toggle"
    >
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}

function App() {
  // sidebar width settings
  const style = {
    "--sidebar-width": "15rem",
    "--sidebar-width-icon": "3rem",
  };

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <AppProvider>
          <Router hook={useHashLocation}>
            <SidebarProvider style={style as React.CSSProperties}>
              <div className="flex h-screen w-full">
                <AppSidebar />
                <div className="flex flex-col flex-1 min-w-0">
                  {/* top header bar with sidebar toggle and theme switch */}
                  <header className="flex items-center justify-between gap-2 px-4 py-2 border-b bg-background/80 backdrop-blur-sm">
                    <SidebarTrigger data-testid="button-sidebar-toggle" />
                    <ThemeToggle />
                  </header>
                  {/* main content area - scrollable */}
                  <main className="flex-1 overflow-auto p-6">
                    <AppRouter />
                  </main>
                </div>
              </div>
            </SidebarProvider>
          </Router>
          <Toaster />
        </AppProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
