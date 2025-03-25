import { useEffect, useState } from "react";

function Home() {
  const [summaryTime, setSummaryTime] = useState("08:00");
  const [emailSummaries, setEmailSummaries] = useState([]);
  const [email, setEmail] = useState("");

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const userEmail = urlParams.get("email");
    if (userEmail) {
      setEmail(userEmail);
      fetchSummaries(userEmail);
    }
  }, []);

  const fetchSummaries = async (userEmail) => {
    try {
      const res = await fetch(`http://localhost:8000/emails?user_email=${userEmail}`);
      const data = await res.json();
      if (Array.isArray(data)) setEmailSummaries(data);
      else console.error("Unexpected summary format", data);
    } catch (err) {
      console.error("Failed to fetch emails", err);
    }
  };

  const handleTimeSave = async () => {
    try {
      await fetch(`http://localhost:8000/update-summary-time`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, summary_time: summaryTime }),
      });
      alert("Summary time updated!");
    } catch (err) {
      console.error("Failed to update summary time", err);
    }
  };

  return (
    <div className="min-h-screen px-4 py-8 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 transition-colors">
      <div className="max-w-3xl mx-auto space-y-10">
        <h1 className="text-3xl font-bold">Welcome, {email || "User"} 👋</h1>

        <div className="border dark:border-gray-700 rounded-xl p-6 shadow-sm bg-gray-50 dark:bg-gray-800 space-y-4">
          <h2 className="text-xl font-semibold">⏰ Set Your Daily Summary Time</h2>
          <div className="flex items-center gap-4">
            <input
              type="time"
              value={summaryTime}
              onChange={(e) => setSummaryTime(e.target.value)}
              className="border rounded px-4 py-2 dark:bg-gray-700 dark:border-gray-600"
            />
            <button
              onClick={handleTimeSave}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded transition"
            >
              Save Time
            </button>
          </div>
        </div>

        <div className="space-y-6">
          <h2 className="text-xl font-semibold">📬 Recent Important Emails</h2>
          {emailSummaries.length > 0 ? (
            <ul className="space-y-4">
              {emailSummaries.map((email, idx) => (
                <li key={idx} className="border-b pb-4 dark:border-gray-700">
                  <div className="font-medium">{email.subject}</div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    From: {email.sender}
                  </div>
                  <div className="text-sm mt-1">{email.snippet}</div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-gray-500 dark:text-gray-400">No summaries available yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default Home;