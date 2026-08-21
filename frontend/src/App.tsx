import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import { ToastProvider } from "./contexts/ToastContext";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AdminRoute } from "./components/AdminRoute";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { Dashboard } from "./pages/Dashboard";
import { CreateTask } from "./pages/CreateTask";
import { TaskDetail } from "./pages/TaskDetail";
import { Hotlist } from "./pages/Hotlist";
import { Profile } from "./pages/Profile";
import { AdminUsers } from "./pages/AdminUsers";
import { ContentAssets } from "./pages/ContentAssets";
import { KnowledgeBase } from "./pages/KnowledgeBase";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<Layout />}>
                <Route path="/" element={<Dashboard />} />
                <Route path="/create" element={<CreateTask />} />
                <Route path="/tasks/:taskId" element={<TaskDetail />} />
                <Route path="/hotlist" element={<Hotlist />} />
                <Route path="/knowledge" element={<KnowledgeBase />} />
                <Route path="/profile" element={<Profile />} />
                <Route element={<AdminRoute />}>
                  <Route path="/admin/users" element={<AdminUsers />} />
                  <Route path="/admin/content-assets" element={<ContentAssets />} />
                </Route>
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
