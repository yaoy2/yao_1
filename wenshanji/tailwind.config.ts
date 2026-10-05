import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1c1f24",
        mist: "#f4f7f6",
        moss: "#486b54",
        rust: "#a6533b",
        paper: "#fffdf8"
      }
    }
  },
  plugins: []
};

export default config;
