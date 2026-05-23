import { useState, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";

const NAV = [
  { to: "/dashboard", icon: "📊", label: "ダッシュボード" },
  { to: "/collect",   icon: "🔍", label: "データ収集" },
  { to: "/analysis",  icon: "🧠", label: "分析・予測" },
  { to: "/today",     icon: "🏇", label: "今日のレース予測" },
  { to: "/database",  icon: "🗄️", label: "データベース管理" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const location = useLocation();

  // ページ遷移時にサイドバーを閉じる
  useEffect(() => { setOpen(false); }, [location.pathname]);

  // 画面外タップでサイドバーを閉じる
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const sidebar = document.getElementById("sidebar");
      if (sidebar && !sidebar.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div className="app-layout">
      {/* モバイル用トップバー */}
      <header className="mobile-header">
        <button className="hamburger" onClick={() => setOpen((v) => !v)} aria-label="メニュー">
          <span /><span /><span />
        </button>
        <span className="mobile-title">JRA Tracking</span>
      </header>

      {/* オーバーレイ */}
      {open && <div className="sidebar-overlay" onClick={() => setOpen(false)} />}

      {/* サイドバー */}
      <aside id="sidebar" className={`sidebar${open ? " sidebar-open" : ""}`}>
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
