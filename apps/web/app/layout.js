import './globals.css';

export const metadata = {
  title: 'TripLens — Dual-Input Accident Analysis',
  description: 'READ-ONLY EVENT + RAW accident analysis workspace',
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
