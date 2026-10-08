import { NavLink, Route, Routes } from "react-router-dom";
import { Dashboard } from "./features/Dashboard";
import { Applications } from "./features/Applications";
import { ApplicationOverview } from "./features/ApplicationOverview";
import { Findings } from "./features/Findings";
import { DpiaRecords } from "./features/DpiaRecords";
import { DpiaList, DpiaWorkspace } from "./features/Dpia";
import { Inventory } from "./features/Inventory";
import { Users } from "./features/Users";
import { Login } from "./features/Login";
import { useAuth } from "./lib/auth";

const ROLE_LABEL: Record<string, string> = {
  admin: "Admin",
  dpo: "DPO",
  auditor: "Auditor",
  owner: "Owner",
  operator: "Operator",
};

function Sidebar() {
  const { user, logout, hasGlobal } = useAuth();
  const roles = user?.global_roles ?? [];
  return (
    <aside className="sidebar">
      <div className="brand">
        PrivacyMon
        <small>DPIA Console · DPDP Act 2023</small>
      </div>
      <nav className="nav">
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/applications">Applications</NavLink>
        {hasGlobal("admin") && <NavLink to="/users">Users &amp; roles</NavLink>}
      </nav>
      <div style={{ marginTop: "auto" }} />
      {user && (
        <div className="user-menu">
          <div className="user-id">
            <span className="user-name">{user.display_name ?? user.email}</span>
            <span className="user-roles">
              {roles.length ? roles.map((r) => ROLE_LABEL[r] ?? r).join(" · ") : "Application access"}
            </span>
          </div>
          <button className="btn" onClick={logout} style={{ width: "100%" }}>
            Sign out
          </button>
        </div>
      )}
    </aside>
  );
}

export function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="login-screen">
        <div className="muted">Loading…</div>
      </div>
    );
  }

  if (!user) return <Login />;

  return (
    <div className="app">
      <Sidebar />
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/applications" element={<Applications />} />
          <Route path="/applications/:id" element={<ApplicationOverview />} />
          <Route path="/applications/:id/findings" element={<Findings />} />
          <Route path="/applications/:id/inventory" element={<Inventory />} />
          <Route path="/applications/:id/dpia" element={<DpiaRecords />} />
          <Route path="/applications/:id/dpias" element={<DpiaList />} />
          <Route path="/dpias/:dpiaId" element={<DpiaWorkspace />} />
          <Route path="/users" element={<Users />} />
        </Routes>
      </main>
    </div>
  );
}
