import type {Metadata} from 'next';
import {Suspense} from 'react';
import MotionSystem from '@/components/MotionSystem';
import './globals.css';
import './motion.css';
import './knowledge.css';
import './story.css';
import './cursor.css';

export const metadata: Metadata = {
  title: 'MemoryVault AI — A place for everything you know',
  description: 'Save anything. Forget nothing. Find everything. Your personal knowledge, connected.',
};

export default function RootLayout({children}: {children: React.ReactNode}) {
  return <html lang="en"><body>{children}<Suspense fallback={null}><MotionSystem/></Suspense></body></html>;
}
