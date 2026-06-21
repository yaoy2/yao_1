import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "众声室",
  description: "本地多模型圆桌群聊 MVP"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
