import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { EvaluationPage } from "./pages/EvaluationPage";
import { FunnelPage } from "./pages/FunnelPage";
import { LibraryPage } from "./pages/LibraryPage";
import { SecurityPage } from "./pages/SecurityPage";
import { WorkspacePage } from "./pages/WorkspacePage";

function OpenWorkspace() {
  const { id } = useParams();
  return <Navigate to={id ? `/?id=${id}` : "/"} replace />;
}

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<WorkspacePage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/funnel" element={<FunnelPage />} />
            <Route path="/investigation" element={<OpenWorkspace />} />
            <Route path="/investigation/:id" element={<OpenWorkspace />} />
            <Route path="/evidence" element={<OpenWorkspace />} />
            <Route path="/evidence/:id" element={<OpenWorkspace />} />
            <Route path="/agents" element={<OpenWorkspace />} />
            <Route path="/security" element={<SecurityPage />} />
            <Route path="/evaluation" element={<EvaluationPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
