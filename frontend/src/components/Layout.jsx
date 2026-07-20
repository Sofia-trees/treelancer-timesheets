export function Layout({ children }) {
  return (
    <>
      <header className="appbar">
        <div className="brand">
          <span className="mark">🌳</span>
          <span>TREES ENGINEERING</span>
          <span className="sub">Treelancer Timesheets</span>
        </div>
      </header>
      <main className="container">{children}</main>
    </>
  );
}

export function Banner({ kind = "info", children }) {
  if (!children) return null;
  return <div className={`banner ${kind}`}>{children}</div>;
}
