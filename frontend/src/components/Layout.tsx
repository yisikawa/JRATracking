import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/dashboard", icon: "📊", label: "ダッシュボード" },
  { to: "/collect",   icon: "🔍", label: "データ収集" },
  { to: "/analysis",  icon: "🧠", label: "分析・予測" },
  { to: "/today",     icon: "🏇", label: "今日のレース予測" },
  { to: "/database",  icon: "🗄️", label: "データベース管理" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>JRA Tracking</h1>
          <p>Bayesian Inference</p>
        </div>
        <nav className="sidebar-nav">
          {NAV.map(({ to, icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            >
              <span className="nav-icon">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}
