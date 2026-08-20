import { Link, useLocation } from "react-router-dom";

export default function Navbar() {
  const location = useLocation();
  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <Link to="/">Engineering Drawing Analysis</Link>
      </div>
      <div className="navbar-links">
        <Link to="/" className={location.pathname === "/" ? "active" : ""}>
          Upload
        </Link>
        <Link
          to="/history"
          className={location.pathname === "/history" ? "active" : ""}
        >
          History
        </Link>
      </div>
    </nav>
  );
}
