import "@iframe-resizer/child";
import { Routes, Route } from 'react-router-dom'
import ErrorBoundary from "@/components/common/ErrorBoundary";
import Configuration from "@/pages/Configuration";
import Session from "@/pages/Session";

function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/" element={<Session />} />
        <Route path="/extension/main" element={<Session />} />
        <Route path="/extension/configuration" element={<Configuration />} />
      </Routes>
    </ErrorBoundary>
  )
}

export default App
