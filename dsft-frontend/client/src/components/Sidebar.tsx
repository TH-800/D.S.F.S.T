// Sidebar.tsx - the main navigation sidebar for the dashboard
// uses the shadcn sidebar component so we get collapse/expand for free
// each nav item links to a different page of the app

import { Link, useLocation } from "wouter";
import { LayoutDashboard, FlaskConical, ScrollText, FileBarChart } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarHeader,
} from "@/components/ui/sidebar";

// the pages we want in the sidebar
const navItems = [
  { title: "Dashboard", url: "/", icon: LayoutDashboard },
  { title: "Experiments", url: "/experiments", icon: FlaskConical },
  { title: "Logs", url: "/logs", icon: ScrollText },
  { title: "Reports", url: "/reports", icon: FileBarChart },
];

export function AppSidebar() {
  const [location] = useLocation();

  return (
    <Sidebar>
      {/* logo and app name at the top */}
      <SidebarHeader className="p-4">
        <div className="flex items-center gap-3">
          {/* simple SVG logo - a broken circle representing chaos/disruption */}
          <svg
            width="32"
            height="32"
            viewBox="0 0 32 32"
            fill="none"
            aria-label="D.S.F.S.T. Logo"
          >
            {/* outer broken ring */}
            <path
              d="M16 3 A13 13 0 0 1 29 16"
              stroke="hsl(213 94% 52%)"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            <path
              d="M29 16 A13 13 0 0 1 16 29"
              stroke="hsl(142 71% 45%)"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            <path
              d="M16 29 A13 13 0 0 1 3 16"
              stroke="hsl(38 92% 50%)"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            <path
              d="M3 16 A13 13 0 0 1 16 3"
              stroke="hsl(0 72% 51%)"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            {/* center dot */}
            <circle cx="16" cy="16" r="3" fill="hsl(213 94% 52%)" />
          </svg>
          <div>
            <h1 className="text-sm font-bold tracking-wide">D.S.F.S.T.</h1>
            <p className="text-xs text-muted-foreground">Chaos Engineering</p>
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => {
                // check if this nav item is the current page
                const isActive = location === item.url;
                return (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive}
                      data-testid={`nav-${item.title.toLowerCase()}`}
                    >
                      <Link href={item.url}>
                        <item.icon className="h-4 w-4" />
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
