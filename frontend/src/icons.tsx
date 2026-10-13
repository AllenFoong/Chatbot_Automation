// 画面上的小图示（自己画的 SVG，不用图示套件，D30）。颜色跟着文字（currentColor），读屏软件不念（aria-hidden）。

import type { ReactNode } from "react";

function Icon({ children, size = 18 }: { children: ReactNode; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

type P = { size?: number };

export const ToothIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M7.5 3.5c-2.5 0-4 2-4 4.6 0 2.6 1.2 4.2 1.8 6.6.5 2 .8 5.8 2.6 5.8 1.6 0 1.6-3.6 2.4-5 .4-.7 1-.9 1.7-.9s1.3.2 1.7.9c.8 1.4.8 5 2.4 5 1.8 0 2.1-3.8 2.6-5.8.6-2.4 1.8-4 1.8-6.6 0-2.6-1.5-4.6-4-4.6-1.8 0-2.6 1-4.5 1s-2.7-1-4.5-1z" />
  </Icon>
);

export const BellIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M6 16v-5a6 6 0 1 1 12 0v5l1.5 2h-15z" />
    <path d="M10 20.5a2 2 0 0 0 4 0" />
  </Icon>
);

export const ChatIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M20.5 14.5a2 2 0 0 1-2 2H8l-4.5 4V5.5a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z" />
  </Icon>
);

export const ClipboardIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M9 3.5h6v3H9z" />
    <path d="M8 5H6.5a1.5 1.5 0 0 0-1.5 1.5v13A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5v-13A1.5 1.5 0 0 0 17.5 5H16" />
    <path d="M9 12h6M9 16h4" />
  </Icon>
);

export const SlidersIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M4 6.5h9M17 6.5h3M4 12h3M11 12h9M4 17.5h11M19 17.5h1" />
    <circle cx="15" cy="6.5" r="2" />
    <circle cx="9" cy="12" r="2" />
    <circle cx="17" cy="17.5" r="2" />
  </Icon>
);

export const UsersIcon = ({ size }: P) => (
  <Icon size={size}>
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5" />
    <circle cx="17" cy="9" r="2.5" />
    <path d="M16.5 14.6c2.6.3 4.5 2.3 4.5 5.4" />
  </Icon>
);

export const LogOutIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
    <path d="M10 16l-4-4 4-4M6 12h10" />
  </Icon>
);

export const RefreshIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M20 11.5a8 8 0 1 0-2.4 5.7" />
    <path d="M20 4.5v7h-7" />
  </Icon>
);

export const CopyIcon = ({ size }: P) => (
  <Icon size={size}>
    <rect x="9" y="9" width="11" height="11" rx="2" />
    <path d="M5.5 15H5a1.5 1.5 0 0 1-1.5-1.5V5A1.5 1.5 0 0 1 5 3.5h8.5A1.5 1.5 0 0 1 15 5v.5" />
  </Icon>
);

export const WhatsAppIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M20.5 11.6a8.5 8.5 0 0 1-12.4 7.6L3.5 20.5l1.4-4.4A8.5 8.5 0 1 1 20.5 11.6z" />
    <path d="M9 9.2c0 3 2.4 5.6 5.6 5.8" />
  </Icon>
);

export const CheckIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </Icon>
);

export const AlertIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M12 4l9 15.5H3z" />
    <path d="M12 10v4.5M12 17.2v.2" />
  </Icon>
);

export const InfoIcon = ({ size }: P) => (
  <Icon size={size}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 11v5.5M12 7.8v.2" />
  </Icon>
);

export const CalendarIcon = ({ size }: P) => (
  <Icon size={size}>
    <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
    <path d="M3.5 10h17M8 3v4M16 3v4" />
  </Icon>
);

export const ChevronLeftIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M14.5 6l-6 6 6 6" />
  </Icon>
);

export const ChevronRightIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M9.5 6l6 6-6 6" />
  </Icon>
);

export const InboxIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M3.5 13.5l2.8-8h11.4l2.8 8v5a1.5 1.5 0 0 1-1.5 1.5H5a1.5 1.5 0 0 1-1.5-1.5z" />
    <path d="M3.5 13.5h5l1.5 2.5h4l1.5-2.5h5" />
  </Icon>
);

export const DownloadIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19.5h14" />
  </Icon>
);

export const MenuIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M4 6.5h16M4 12h16M4 17.5h16" />
  </Icon>
);

export const CloseIcon = ({ size }: P) => (
  <Icon size={size}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
);
