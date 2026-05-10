import "@iframe-resizer/child";
import { Routes, Route } from 'react-router-dom'
import Configuration from "@/pages/Configuration";
import Session from "@/pages/Session";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Session />} />
      <Route path="/extension/main" element={<Session />} />
      <Route path="/extension/configuration" element={<Configuration />} />
    </Routes>
  )
}

export default App
