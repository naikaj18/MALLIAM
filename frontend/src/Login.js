import { useState } from "react";
import { EnvelopeIcon } from "@heroicons/react/24/solid";

function Login() {
  const [isRedirecting, setIsRedirecting] = useState(false);

  const handleLogin = () => {
    setIsRedirecting(true);
    window.location.href = "http://localhost:8000/auth/login";
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-white px-4">
      <div className="max-w-md w-full text-center space-y-8 animate-fade-in">
        <EnvelopeIcon className="w-16 h-16 text-accentBlue mx-auto" />

        <h1 className="text-4xl font-semibold text-textPrimary">Welcome to Mailliam</h1>
        <p className="text-textSecondary">Your smart email summary assistant</p>

        <button
          onClick={handleLogin}
          className={`w-full mt-6 py-3 ${
            isRedirecting ? "bg-gray-300" : "bg-black hover:bg-gray-900"
          } text-white rounded-xl text-lg transition font-medium`}
          disabled={isRedirecting}
        >
          {isRedirecting ? "Redirecting..." : "Sign in with Google"}
        </button>
      </div>
    </div>
  );
}

export default Login;