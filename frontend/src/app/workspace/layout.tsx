'use client';

import { useState } from 'react';
import { DataDrop } from './components/data-drop';
import { Chat } from './components/chat';
import { Contact } from './components/contact';
import { WorkspaceSidebar } from './components/workspace-sidebar';
import { SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar';
import { FadeUp } from '@/components/fade-up';

type ContactData = {
  text: string;
  email: string;
  subject: string;
};

export default function WorkspaceLayout() {
  const [contactData, setContactData] = useState<ContactData | null>(null);

  const currentUser = {
    id: 'user-1',
    email: 'max@pmatch.com',
    username: 'Max',
  };
  return (
    <SidebarProvider>
      <div className="flex min-h-screen w-full lg:h-screen">
        <WorkspaceSidebar currentUser={currentUser} />

        <main className="flex-1 lg:overflow-hidden">
          <div className="bg-background min-h-screen py-4 pr-1 pl-1 md:pr-4 lg:h-full lg:overflow-hidden">
            <div className="absolute top-6 right-6 z-50 md:hidden">
              <SidebarTrigger className="h-8 w-8 text-lg" />
            </div>

            <div className="flex min-h-full flex-col gap-4 lg:h-full lg:flex-row">
              <div className="flex w-full flex-col gap-4 lg:w-2/5">
                <FadeUp
                  className="border-border h-[350px] overflow-hidden border-2 lg:h-3/7"
                  delay={0.02}
                >
                  <DataDrop />
                </FadeUp>

                <FadeUp
                  className="border-border h-[500px] overflow-hidden border-2 lg:h-4/7"
                  delay={0.06}
                >
                  <Chat onContactDataUpdate={setContactData} />
                </FadeUp>
              </div>

              <FadeUp
                className="border-border h-[700px] w-full overflow-hidden border-2 lg:h-auto lg:w-3/5"
                delay={0.1}
              >
                <Contact incomingContactData={contactData} onContactDataUpdate={setContactData} />
              </FadeUp>
            </div>
          </div>
        </main>
      </div>
    </SidebarProvider>
  );
}
