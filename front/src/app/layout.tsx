// src/app/layout.tsx
import "@/app/globals.css";
import Header from "@/components/layout/Header";
import Footer from "@/components/layout/Footer";
import { AuthModalProvider } from "@/context/AuthModalContext";
import { AuthModal } from "@/components/auth/AuthModal";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className="no-scrollbar" data-scroll-behavior="smooth">
      <body className="bg-gray-50 text-gray-900 flex flex-col min-h-screen">
        <AuthModalProvider>
          <Header />

          <div className="flex-1 pt-16">
            {children}
          </div>

          <Footer />
          <AuthModal />
        </AuthModalProvider>
      </body>
    </html>
  );
}