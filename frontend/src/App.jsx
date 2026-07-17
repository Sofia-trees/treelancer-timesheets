import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import { Layout } from "./components/Layout.jsx";
import FreelancerDashboard from "./pages/FreelancerDashboard.jsx";
import TimesheetEditor from "./pages/TimesheetEditor.jsx";

export default function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return <Layout><p className="muted">Loading…</p></Layout>;
  }

  if (!user) {
    return (
      <Layout>
        <p className="muted">
          Couldn't reach the backend. Make sure the API is running, then reload.
        </p>
      </Layout>
    );
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<FreelancerDashboard />} />
        <Route path="/timesheets/:id" element={<TimesheetEditor />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Layout>
  );
}
