"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/agents", label: "Agents" },
  { href: "/marketplace", label: "Marketplace" },
  { href: "/approvals", label: "Approvals" },
  { href: "/billing", label: "Billing" },
  { href: "/notifications", label: "Notifications" },
  { href: "/integrations", label: "Integrations" },
];

export default function Nav() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  if (!user) return null;

  const links = user.role === "platform_admin" ? [...LINKS, { href: "/admin", label: "Admin" }] : LINKS;

  return (
    <nav className="nav">
      <div className="nav-links">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`nav-link${pathname === link.href ? " active" : ""}`}
          >
            {link.label}
          </Link>
        ))}
      </div>
      <div className="row" style={{ gap: 12 }}>
        <span className="muted small">
          {user.email} · {user.role}
        </span>
        <button
          className="btn"
          onClick={() => {
            logout();
            router.replace("/login");
          }}
        >
          Sign out
        </button>
      </div>
    </nav>
  );
}
