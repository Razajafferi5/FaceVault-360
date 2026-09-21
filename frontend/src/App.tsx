import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, ProtectedRoute, useAuth } from './context/AuthContext';
import { Layout } from './components/layout/Layout';
import { Login } from './pages/Login';
import { Signup } from './pages/Signup';
import { Dashboard } from './pages/Dashboard';
import { LiveRecognition } from './pages/LiveRecognition';
import { Enrollment } from './pages/Enrollment';
import { Attendance } from './pages/Attendance';
import { People } from './pages/People';
import { Logs } from './pages/Logs';
import { Testing } from './pages/Testing';
import { Analytics } from './pages/Analytics';
import { Settings } from './pages/Settings';
import { Cameras } from './pages/Cameras';
import { UnknownPersons } from './pages/UnknownPersons';
import { StaffDashboard } from './pages/StaffDashboard';
import { StaffAttendance } from './pages/StaffAttendance';
import { StaffProfile } from './pages/StaffProfile';
import { OwnerManagement } from './pages/OwnerManagement';

function HomeRoute() {
  const { isOwner } = useAuth();
  return isOwner ? <Dashboard /> : <StaffDashboard />;
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public Authentication Routes */}
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          {/* Protected Application Base Layout */}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            {/* Dynamic Home Route */}
            <Route index element={<HomeRoute />} />

            {/* Staff-Accessible Routes */}
            <Route path="staff-dashboard" element={<StaffDashboard />} />
            <Route path="my-attendance" element={<StaffAttendance />} />
            <Route path="profile" element={<StaffProfile />} />
            <Route path="live" element={<LiveRecognition />} />
            <Route path="testing" element={<Testing />} />

            {/* Owner-Protected Routes */}
            <Route
              path="unknowns"
              element={
                <ProtectedRoute requireOwner>
                  <UnknownPersons />
                </ProtectedRoute>
              }
            />
            <Route
              path="attendance"
              element={
                <ProtectedRoute requireOwner>
                  <Attendance />
                </ProtectedRoute>
              }
            />
            <Route
              path="cameras"
              element={
                <ProtectedRoute requireOwner>
                  <Cameras />
                </ProtectedRoute>
              }
            />
            <Route
              path="enroll"
              element={
                <ProtectedRoute requireOwner>
                  <Enrollment />
                </ProtectedRoute>
              }
            />
            <Route
              path="people"
              element={
                <ProtectedRoute requireOwner>
                  <People />
                </ProtectedRoute>
              }
            />
            <Route
              path="owner-management"
              element={
                <ProtectedRoute requireOwner>
                  <OwnerManagement />
                </ProtectedRoute>
              }
            />
            <Route
              path="logs"
              element={
                <ProtectedRoute requireOwner>
                  <Logs />
                </ProtectedRoute>
              }
            />
            <Route
              path="analytics"
              element={
                <ProtectedRoute requireOwner>
                  <Analytics />
                </ProtectedRoute>
              }
            />
            <Route
              path="settings"
              element={
                <ProtectedRoute requireOwner>
                  <Settings />
                </ProtectedRoute>
              }
            />
          </Route>

          {/* Fallback to root */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
