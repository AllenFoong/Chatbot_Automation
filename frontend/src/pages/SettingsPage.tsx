// 诊所设置（D14）：所有员工都能看，只有 ADMIN 能改（D25）。
// STAFF 看到的是同样的画面，但没有修改的按钮。后端也会挡（403），画面只是不让人按到。
// 改了马上生效：空档计算每次都从数据库读设置。

import { NavLink, Navigate, useParams } from "react-router";
import { useAuth } from "../auth";
import { Notice, PageHeader } from "../components";
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
    <div className="page">
      <PageHeader
        title="Settings"
        description="Doctors, treatments and closure days. Free slots and the reminder list use these settings."
      />
      <nav className="tabs" aria-label="Settings sections">
        {Object.entries(SECTIONS).map(([key, s]) => (
          <NavLink key={key} to={`/settings/${key}`} className={({ isActive }) => (isActive ? "tab active" : "tab")}>
            {s.label}
          </NavLink>
        ))}
      </nav>
      {!isAdmin && <Notice tone="info">You can view the settings. Only an admin can change them.</Notice>}
      <Component canEdit={isAdmin} />
    </div>
  );
}
