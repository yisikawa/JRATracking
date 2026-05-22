import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import DataCollection from "./pages/DataCollection";
import Analysis from "./pages/Analysis";
import TodaysPrediction from "./pages/TodaysPrediction";
import DatabaseManager from "./pages/DatabaseManager";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/collect" element={<DataCollection />} />
        <Route path="/analysis" element={<Analysis />} />
        <Route path="/today" element={<TodaysPrediction />} />
        <Route path="/database" element={<DatabaseManager />} />
      </Routes>
    </Layout>
  );
}
