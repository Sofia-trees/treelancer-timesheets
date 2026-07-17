import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import { Layout } from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
import VerifyLogin from "./pages/VerifyLogin.jsx";
import FreelancerDashboard from "./pages/FreelancerDashboard.jsx";
import TimesheetEditor from "./pages/TimesheetEditor.jsx";
import ManagerQueue from "./pages/ManagerQueue.jsx";
import AdminTimesheets from "./pages/AdminTimesheets.jsx";
import AdminAssignments from "./pages/AdminAssignments.jsx";

function Home() {
  const { user } = useAuth();
  if (user.role === "admin") return <Navigate to="/admin" replace />;
  if (user.role === "line_manager") return <Navigate to="/manager" replace />;
  return <Navigate to="/dashboard" replace />;
}

export default function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return <Layout><p className="muted">Loading…</p></Layout>;
  }

  if (!user) {
    return (
      <Layout>
        <Routes>
          <Route path="/login/verify" element={<VerifyLogin />} />
          <Route path="*" element={<Login />} />
        </Routes>
      </Layout>
    );
  }

  return (
    <Layout>
      <Routes>
        {/* Always available so a magic link works even with a stale session. */}
        <Route path="/login/verify" element={<VerifyLogin />} />
        <Route path="/" element={<Home />} />
        <Route path="/dashboard" element={<Guard role="freelancer"><FreelancerDashboard /></Guard>} />
        <Route path="/timesheets/:id" element={<Guard role="freelancer"><TimesheetEditor /></Guard>} />
        <Route path="/manager" element={<Guard role="line_manager"><ManagerQueue /></Guard>} />
        <Route path="/admin" element={<Guard role="admin"><AdminTimesheets /></Guard>} />
        <Route path="/admin/assignments" element={<Guard role="admin"><AdminAssignments /></Guard>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

function Guard({ role, children }) {
  const { user } = useAuth();
  return user.role === role ? children : <Navigate to="/" replace />;
}
