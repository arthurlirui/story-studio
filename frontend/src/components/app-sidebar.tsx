"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import {
  LayoutDashboard,
  BookOpen,
  Briefcase,
  Settings,
  Sparkles,
  Sun,
  Moon,
} from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";

const navItems = [
  { href: "/", label: "仪表盘", icon: LayoutDashboard },
  { href: "/novels", label: "小说项目", icon: BookOpen },
  { href: "/novels/new", label: "创建新小说", icon: Sparkles },
  { href: "/jobs", label: "后台任务", icon: Briefcase },
  { href: "/settings", label: "设置", icon: Settings },
];

export function AppSidebar() {
  const pathname = usePathname();
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <Sidebar>
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-1.5">
          <Sparkles className="h-6 w-6 text-primary" />
          <div className="flex flex-col">
            <span className="text-sm font-semibold font-heading">Story Studio</span>
            <span className="text-xs text-muted-foreground">AI 小说创作平台</span>
          </div>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>导航</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => {
                const active =
                  pathname === item.href ||
                  (item.href !== "/" && pathname.startsWith(item.href));
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton isActive={active} render={
                      <Link href={item.href}>
                        <item.icon className="h-4 w-4" />
                        <span>{item.label}</span>
                      </Link>
                    } />
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <div className="flex items-center justify-between px-2 py-1.5">
          <span className="text-xs text-muted-foreground">14 Agents · 去AI化引擎</span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label="切换主题"
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
          >
            <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
          </Button>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
