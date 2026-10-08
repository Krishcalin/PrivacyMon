import { NavLink, Route, Routes } from "react-router-dom";
import { Dashboard } from "./features/Dashboard";
import { Applications } from "./features/Applications";
import { ApplicationOverview } from "./features/ApplicationOverview";
import { Findings } from "./features/Findings";
import { DpiaRecords } from "./features/DpiaRecords";

function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        PrivacyMon
        <small>DPIA Console · DPDP Act 2023</small>
      </div>
      <nav className="nav">
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/applications">Applications</NavLink>
      </nav>
      <div style={{ marginTop: "auto" }} />
    </aside>
  );
}

export function App() {
  return (
    <div className="app">
      <Sidebar />
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/applications" element={<Applications />} />
          <Route path="/applications/:id" element={<ApplicationOverview />} />
          <Route path="/applications/:id/findings" element={<Findings />} />
          <Route path="/applications/:id/dpia" element={<DpiaRecords />} />
        </Routes>
      </main>
    </div>
  );
}
