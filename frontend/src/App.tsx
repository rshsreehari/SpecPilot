import { Route, Routes } from 'react-router-dom'
import { AppShellProvider } from './context/AppShellContext'
import { Layout } from './components/Layout'
import { AskScreen } from './screens/AskScreen'
import { EvaluationScreen } from './screens/EvaluationScreen'
import { EndpointsScreen } from './screens/EndpointsScreen'
import { EndpointDetailScreen } from './screens/EndpointDetailScreen'
import { ApisScreen } from './screens/ApisScreen'

function App() {
  return (
    <AppShellProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<AskScreen />} />
          <Route path="evaluation" element={<EvaluationScreen />} />
          <Route path="evaluation/:reportId" element={<EvaluationScreen />} />
          <Route path="endpoints" element={<EndpointsScreen />} />
          <Route path="endpoints/:endpointId" element={<EndpointDetailScreen />} />
          <Route path="apis" element={<ApisScreen />} />
        </Route>
      </Routes>
    </AppShellProvider>
  )
}

export default App
