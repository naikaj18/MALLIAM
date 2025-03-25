import { useEffect, useState } from "react";

function ThemeToggleButton() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const root = window.document.documentElement;
    if (isDark) {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
  }, [isDark]);

  return (
    <div className="p-4 text-right transition-opacity duration-500 ease-in-out opacity-100">
      <button
        onClick={() => setIsDark(!isDark)}
        className={`px-4 py-2 rounded bg-accentBlue text-white transition-colors duration-500 ease-in-out ${
          isDark ? "hover:bg-yellow-500" : "hover:bg-blue-700"
        }`}
      >
        {isDark ? "☀️ Light Mode" : "🌙 Dark Mode"}
      </button>
    </div>
  );
}

export default ThemeToggleButton;