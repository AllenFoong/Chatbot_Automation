// 诊所设置（D14）：所有员工都能看，只有 ADMIN 能改（D25）。
// STAFF 看到的是同样的画面，但没有修改的按钮。后端也会挡（403），画面只是不让人按到。
// 改了马上生效：空档计算每次都从数据库读设置。

import { NavLink, Navigate, useParams } from "react-router";
import { useAuth } from "../auth";
import { Notice, Page, PageHeader } from "../components";
import ClinicSection from "./settings/ClinicSection";
import ClosuresSection from "./settings/ClosuresSection";
import DoctorsSection from "./settings/DoctorsSection";
import LeavesSection from "./settings/LeavesSection";
import ServicesSection from "./settings/ServicesSection";

const SECTIONS = {
  doctors: { label: "Doctors & schedules", Component: DoctorsSection },
  services: { label: "Treatments", Component: ServicesSection },
  closures: { label: "Clinic closures", Component: ClosuresSection },
  leaves: { label: "Doctor leave", Component: LeavesSection },
  clinic: { label: "Slots & auto-confirm", Component: ClinicSection },
} as const;

type SectionKey = keyof typeof SECTIONS;

export default function SettingsPage() {
  const { section } = useParams();
  const { isAdmin } = useAuth();
  if (!section || !(section in SECTIONS)) return <Navigate to="/settings/doctors" replace />;
  const { Component } = SECTIONS[section as SectionKey];

  return (
    <Page>
      <PageHeader
        title="Settings"
        description="Doctors, treatments and closure days. Free slots and the reminder list use these settings."
      />
      {/* 和 shadcn 的 Tabs 一样的样子；每一块有自己的网址（重新整理还在同一块） */}
      <nav
        aria-label="Settings sections"
        className="inline-flex w-fit max-w-full flex-wrap items-center gap-1 rounded-lg bg-secondary p-1 text-muted-foreground"
      >
        {Object.entries(SECTIONS).map(([key, s]) => (
          <NavLink
            key={key}
            to={`/settings/${key}`}
            className="inline-flex h-8 items-center rounded-md px-3 text-sm font-medium whitespace-nowrap no-underline transition-[color,box-shadow] outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/30 aria-[current=page]:bg-card aria-[current=page]:text-foreground aria-[current=page]:shadow-sm"
          >
            {s.label}
          </NavLink>
        ))}
      </nav>
      {!isAdmin && <Notice tone="info">You can view the settings. Only an admin can change them.</Notice>}
      <Component canEdit={isAdmin} />
    </Page>
  );
}
