import { Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Home from './pages/Home'
import Findings from './pages/Findings'
import About from './pages/About'
import './App.css'

function App() {
  return (
    <>
      <Navbar />
      <main className="page-main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/findings" element={<Findings />} />
          <Route path="/about" element={<About />} />
        </Routes>
      </main>
    </>
  )
}

export default App
