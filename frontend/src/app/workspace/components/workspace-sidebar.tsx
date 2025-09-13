'use client';

import { useState } from 'react';
import { useTheme } from 'next-themes';
import Link from 'next/link';
import {
  Plus,
  Search,
  Moon,
  Sun,
  User,
  Settings,
  Palette,
  Check,
  PanelLeft,
  SmilePlus,
} from 'lucide-react';
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
  SidebarRail,
  SidebarTrigger,
  useSidebar,
} from '@/components/ui/sidebar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

const navigationItems = [
  {
    title: 'New Chat',
    icon: Plus,
  },
  {
    title: 'Search Chats',
    icon: Search,
  },
];

type WorkspaceSidebarProps = {
  currentUser?: {
    id: string;
    email: string;
    username: string;
  };
};

export function WorkspaceSidebar({ currentUser }: WorkspaceSidebarProps) {
  const { theme, setTheme } = useTheme();
  const { open, setOpen } = useSidebar();
  const [isHovering, setIsHovering] = useState(false);

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <Link
              href="/"
              className="flex w-full items-center gap-2 px-2 group-data-[collapsible=icon]:hidden"
            >
              <span className="font-mono text-lg">
                pm<span className="pr-1 -tracking-[0.1em]">atch</span>
              </span>
            </Link>
            <SidebarMenuButton
              onClick={() => setOpen(!open)}
              onMouseEnter={() => setIsHovering(true)}
              onMouseLeave={() => setIsHovering(false)}
              className="hidden w-full cursor-pointer group-data-[collapsible=icon]:flex"
            >
              {isHovering && !open ? <PanelLeft size={16} /> : <SmilePlus size={16} />}
            </SidebarMenuButton>
          </div>
          <SidebarTrigger className="cursor-pointer group-data-[collapsible=icon]:hidden" />
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navigationItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton asChild>
                    <span>
                      <item.icon size={20} />
                      <span className="text-base">{item.title}</span>
                    </span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton>
                  <User size={20} />
                  <span className="text-base">{currentUser?.username || 'User'}</span>
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="top" className="w-56">
                {currentUser && (
                  <>
                    <div className="px-2 py-1.5">
                      <p className="text-sm font-medium">{currentUser.username}</p>
                      <p className="text-muted-foreground truncate text-xs">{currentUser.email}</p>
                    </div>
                    <DropdownMenuSeparator />
                  </>
                )}

                <DropdownMenuSub>
                  <DropdownMenuSubTrigger>
                    <Palette size={16} className="mr-4" />
                    Theme
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent className="w-40">
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setTheme('light');
                      }}
                    >
                      <Sun size={16} className="mr-2" />
                      Light
                      {theme === 'light' && <Check size={12} className="ml-auto" />}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setTheme('dark');
                      }}
                    >
                      <Moon size={16} className="mr-2" />
                      Dark
                      {theme === 'dark' && <Check size={12} className="ml-auto" />}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setTheme('system');
                      }}
                    >
                      <Palette size={16} className="mr-2" />
                      System
                      {theme === 'system' && <Check size={12} className="ml-auto" />}
                    </DropdownMenuItem>
                  </DropdownMenuSubContent>
                </DropdownMenuSub>

                <DropdownMenuItem>
                  <Settings size={16} className="mr-2" />
                  Settings
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
