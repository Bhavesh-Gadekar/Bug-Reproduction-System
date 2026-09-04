import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Bug Reproduction Agent - AI-Powered Automated Bug Repro Pipeline',
  description: 'Autonomous multi-agent system for reproducing, isolating, and validating software bugs.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}
