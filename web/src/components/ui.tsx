import { createElement, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

export type IconName =
  | "arrow"
  | "bell"
  | "bookmark"
  | "calendar"
  | "check"
  | "chevron"
  | "close"
  | "compass"
  | "filter"
  | "home"
  | "plus"
  | "search"
  | "settings"
  | "user"
  | "link"
  | "video"
  | "camera"
  | "upload"
  | "play"
  | "users"
  | "shield"
  | "code"
  | "trash"
  | "copy"
  | "phone"
  | "mic"
  | "mic-off"
  | "video-off";

const paths: Record<IconName, ReactNode> = {
  arrow: <path d="m5 12 5 5L20 7" />,
  bell: <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />,
  bookmark: <path d="M6 3h12v18l-6-4-6 4z" />,
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M16 3v4M8 3v4M3 11h18" />
    </>
  ),
  check: <path d="m5 12 4 4L19 6" />,
  chevron: <path d="m9 18 6-6-6-6" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  compass: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m15 9-2 4-4 2 2-4z" />
    </>
  ),
  filter: <path d="M4 6h16M7 12h10M10 18h4" />,
  home: (
    <>
      <path d="m3 11 9-8 9 8" />
      <path d="M5 10v10h14V10M9 20v-6h6v6" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4-4" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M4.9 4.9 7 7M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </>
  ),
  link: (
    <>
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </>
  ),
  video: (
    <>
      <rect x="2" y="6" width="14" height="12" rx="2" />
      <path d="m22 8-6 4 6 4V8Z" />
    </>
  ),
  camera: (
    <>
      <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z" />
      <circle cx="12" cy="13" r="3" />
    </>
  ),
  upload: (
    <>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </>
  ),
  play: <polygon points="5 3 19 12 5 21 5 3" />,
  users: (
    <>
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </>
  ),
  shield: (
    <>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </>
  ),
  code: (
    <>
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </>
  ),
  trash: (
    <>
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </>
  ),
  copy: (
    <>
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </>
  ),
  phone: (
    <>
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
    </>
  ),
  mic: (
    <>
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </>
  ),
  "mic-off": (
    <>
      <line x1="1" y1="1" x2="23" y2="23" />
      <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6" />
      <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </>
  ),
  "video-off": (
    <>
      <path d="M16 16v1a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2m5.66 0H14a2 2 0 0 1 2 2v3.34l1 1L22 8v8" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </>
  ),
};

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      className="icon"
      viewBox="0 0 24 24"
      width={size}
      height={size}
    >
      {paths[name]}
    </svg>
  );
}

export function Text({
  as = "div",
  className = "",
  children,
}: {
  as?: "div" | "h1" | "h2" | "h3" | "p" | "span";
  className?: string;
  children: ReactNode;
}) {
  return createElement(as, { className }, children);
}

export function Button({
  children,
  variant = "primary",
  icon,
  disabled = false,
  type = "button",
  onClick,
}: {
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost";
  icon?: IconName;
  disabled?: boolean;
  type?: "button" | "submit";
  onClick?: () => void;
}) {
  return (
    <button
      type={type}
      className={`btn btn-${variant}`}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
      {icon && <Icon name={icon} size={17} />}
    </button>
  );
}

export function Field({
  label,
  placeholder,
  icon,
  type = "text",
  value,
  onChange,
}: {
  label: string;
  placeholder: string;
  icon?: IconName;
  type?: string;
  value?: string;
  onChange?: (value: string) => void;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <span className="input-shell">
        {icon && <Icon name={icon} size={18} />}
        <input
          type={type}
          placeholder={placeholder}
          aria-label={label}
          value={value}
          onChange={(e) => onChange?.(e.target.value)}
        />
      </span>
    </label>
  );
}

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand ${compact ? "brand-compact" : ""}`}>
      <span className="brand-mark">
        <span />
      </span>
      <Text as="span">CLEAR</Text>
    </div>
  );
}

export function TopBar({
  title,
  action = "bell",
}: {
  title: string;
  action?: IconName;
}) {
  return (
    <div className="topbar">
      <Text as="h3">{title}</Text>
      <span className="icon-button">
        <Icon name={action} />
      </span>
    </div>
  );
}

type TabItem = { name: IconName; label: string; path: string };

const userTabs: TabItem[] = [
  { name: "home", label: "Home", path: "/" },
  { name: "link", label: "Connect", path: "/connections" },
  { name: "plus", label: "Pair", path: "/pair" },
  { name: "video", label: "Videos", path: "/videos" },
  { name: "user", label: "Profile", path: "/profile" },
];

const adminTabs: TabItem[] = [
  { name: "home", label: "Home", path: "/" },
  { name: "shield", label: "Admin", path: "/admin" },
  { name: "plus", label: "Pair", path: "/pair" },
  { name: "video", label: "Videos", path: "/videos" },
  { name: "user", label: "Profile", path: "/profile" },
];

const devTabs: TabItem[] = [
  { name: "home", label: "Home", path: "/" },
  { name: "code", label: "Dev", path: "/dev" },
  { name: "plus", label: "Pair", path: "/pair" },
  { name: "video", label: "Videos", path: "/videos" },
  { name: "user", label: "Profile", path: "/profile" },
];

export function TabBar({ role = "user" }: { role?: "user" | "admin" | "developer" }) {
  const location = useLocation();
  const navigate = useNavigate();

  const tabs = role === "admin" ? adminTabs : role === "developer" ? devTabs : userTabs;

  return (
    <div className="tabbar">
      {tabs.map((item) => {
        const active =
          item.path === "/"
            ? location.pathname === "/"
            : location.pathname.startsWith(item.path);
        return (
          <div
            className={active ? "active" : ""}
            key={item.name}
            onClick={() => navigate(item.path)}
          >
            <Icon name={item.name} size={19} />
            <span>{item.label}</span>
          </div>
        );
      })}
    </div>
  );
}

export function Avatar({
  initials = "AM",
  small = false,
}: {
  initials?: string;
  small?: boolean;
}) {
  return (
    <span className={`avatar ${small ? "avatar-small" : ""}`}>{initials}</span>
  );
}

export function initialsOf(name?: string | null, email?: string | null) {
  const source = name?.trim() || email?.split("@")[0] || "?";
  const parts = source.split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase() || "?";
}

export function BrandLink({ href, children }: { href: string; children: ReactNode }) {
  return <Link to={href}>{children}</Link>;
}
