import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Login from "./login";
import Home from "./home";
import { useEffect, useState } from "react";

function ThemeToggleButton() {
  const [isDark, setIsDark] = useState(false);
  const currentPath = window.location.pathname;

  useEffect(() => {
    const root = window.document.documentElement;
    const storedTheme = localStorage.getItem("theme");
    if (storedTheme === "dark") {
      root.classList.add("dark");
      setIsDark(true);
    }
  }, []);

  const toggleTheme = () => {
    const root = window.document.documentElement;
    if (isDark) {
      root.classList.remove("dark");
      localStorage.setItem("theme", "light");
    } else {
      root.classList.add("dark");
      localStorage.setItem("theme", "dark");
    }
    setIsDark(!isDark);
  };

  if (currentPath === "/") return null;

  return (
    <div className="absolute top-4 right-4 flex space-x-3 z-50">
      <button
        onClick={toggleTheme}
        className="p-2 rounded-full bg-gray-200 dark:bg-gray-700 text-black dark:text-white shadow-md hover:scale-105 transition"
        title="Toggle Theme"
      >
        {isDark ? "☀️" : "🌙"}
      </button>
      <button
        onClick={() => {
          localStorage.clear();
          window.location.href = "/";
        }}
        className="p-2 rounded-full bg-red-500 text-white shadow-md hover:bg-red-600 transition"
        title="Logout"
      >
        ⎋
      </button>
    </div>
  );
}

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-100 text-black dark:bg-gray-900 dark:text-white transition-colors duration-300">
        <ThemeToggleButton />
        <Routes>
          <Route path="/" element={<Login />} />
          <Route path="/home" element={<Home />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;