import { useAuth } from "../auth.jsx";
import { statusLabel } from "../util.js";

export function Layout({ children }) {
  const { user } = useAuth();
  return (
    <>
      <header className="appbar">
        <div className="brand">
          <span className="mark">🌳</span>
          <span>TREES ENGINEERING</span>
          <span className="sub">Treelancer Timesheets</span>
        </div>
        {user && (
          <div className="who">
            <span>{user.full_name}</span>
          </div>
        )}
      </header>
      <main className="container">{children}</main>
    </>
  );
}

export function StatusBadge({ status }) {
  return <span className={`badge ${status}`}>{statusLabel(status)}</span>;
}

export function Banner({ kind = "info", children }) {
  if (!children) return null;
  return <div className={`banner ${kind}`}>{children}</div>;
}
