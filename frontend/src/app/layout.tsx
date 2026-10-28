import "@/styles/globals.css";
import { type Metadata } from "next";
import { I18nProvider } from "../i18n/context";
import { AuthProvider } from "../features/auth/AuthContext";

export const metadata: Metadata = {
  title: "ΚΤΕΛ Operations SaaS — Επιχειρησιακός Προγραμματισμός",
  description: "Internal operations scheduling platform for Greek KTEL bus transit networks",
  icons: [{ rel: "icon", url: "/favicon.ico" }],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="el">
      <body className="antialiased">
        <I18nProvider>
          <AuthProvider>{children}</AuthProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
