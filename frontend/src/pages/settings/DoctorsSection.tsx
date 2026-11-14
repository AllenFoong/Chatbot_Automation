// 医生和每星期的排班。离职的医生改成 inactive，不删除（旧的预约请求还会用到）。
// 排班的时间只能选 30 分钟的格（数据库也会检查）。

import { useEffect, useState, type FormEvent } from "react";
import * as api from "../../api";
import { CheckIcon, TriangleAlertIcon } from "lucide-react";
import { Badge, Empty, ErrorBox, Field, Loading, SectionTitle } from "../../components";
import { Alert, AlertDescription } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Checkbox } from "../../components/ui/checkbox";
import { Input } from "../../components/ui/input";
import { NativeSelect } from "../../components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import { cn } from "../../lib/utils";
import { HALF_HOURS, formatTime, weekdayName } from "../../format";
import { useAction, useLoad } from "../../hooks";
import { scheduleProblems } from "../../schedule";
import type { Doctor, ScheduleDay } from "../../types";

function TimeSelect({
  label,
  value,
  onChange,
  disabled,
  optional,
}: {
  label: string;
  value: string | null;
  onChange: (value: string | null) => void;
  disabled: boolean;
  optional?: boolean;
}) {
  return (
    <NativeSelect
      aria-label={label}
      value={value ? formatTime(value) : ""}
      onChange={(e) => onChange(e.target.value || null)}
      disabled={disabled}
      className="w-28"
    >
      <option value="">{optional ? "None" : "—"}</option>
      {HALF_HOURS.map((t) => (
        <option key={t} value={t}>
          {t}
        </option>
      ))}
    </NativeSelect>
  );
}

function ScheduleEditor({ doctor, canEdit }: { doctor: Doctor; canEdit: boolean }) {
  const schedule = useLoad(() => api.settings.schedule(doctor.id), [doctor.id]);
  const [days, setDays] = useState<ScheduleDay[]>([]);
  const [saved, setSaved] = useState(false);
  const action = useAction();

  useEffect(() => {
    if (schedule.data) setDays(schedule.data);
  }, [schedule.data]);

  function update(weekday: number, change: Partial<ScheduleDay>) {
    setSaved(false);
    setDays((ds) => ds.map((d) => (d.weekday === weekday ? { ...d, ...change } : d)));
  }

  const problems = scheduleProblems(days);

  async function save() {
    setSaved(false);
    if (problems.length > 0) return;
    if (await action.run(async () => setDays(await api.settings.setSchedule(doctor.id, days)))) setSaved(true);
  }

  if (schedule.data === undefined) {
    return (
      <>
        <ErrorBox message={schedule.error} onRetry={schedule.reload} />
        {schedule.loading && <Loading />}
      </>
    );
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
      <SectionTitle title={`Weekly schedule – ${doctor.display_name}`}>
        "Last slot" is the last time a 30-minute appointment can start. Slots from "break start" up to (not
        including) "break end" cannot be booked.
      </SectionTitle>
      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Day</TableHead>
              <TableHead>Working</TableHead>
              <TableHead>Start</TableHead>
              <TableHead>Last slot</TableHead>
              <TableHead>Break start</TableHead>
              <TableHead>Break end</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {days.map((d) => {
              const name = weekdayName(d.weekday);
              const off = !d.is_working;
              return (
                <TableRow key={d.weekday} className={cn(off && "text-muted-foreground")}>
                  <TableCell className="font-medium">{name}</TableCell>
                  <TableCell>
                    <Checkbox
                      aria-label={`${name} working`}
                      checked={d.is_working}
                      disabled={!canEdit}
                      onChange={(e) => update(d.weekday, { is_working: e.target.checked })}
                    />
                  </TableCell>
                  <TableCell>
                    <TimeSelect label={`${name} start`} value={d.start_time} disabled={!canEdit || off}
                      onChange={(v) => update(d.weekday, { start_time: v })} />
                  </TableCell>
                  <TableCell>
                    <TimeSelect label={`${name} last slot`} value={d.last_slot} disabled={!canEdit || off}
                      onChange={(v) => update(d.weekday, { last_slot: v })} />
                  </TableCell>
                  <TableCell>
                    <TimeSelect label={`${name} break start`} value={d.break_start} disabled={!canEdit || off} optional
                      onChange={(v) => update(d.weekday, { break_start: v })} />
                  </TableCell>
                  <TableCell>
                    <TimeSelect label={`${name} break end`} value={d.break_end} disabled={!canEdit || off} optional
                      onChange={(v) => update(d.weekday, { break_end: v })} />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      {canEdit && problems.length > 0 && (
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertDescription>
            <ul className="m-0 list-disc pl-4">
              {problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
      <ErrorBox message={action.error} />
      {canEdit && (
        <div className="flex items-center gap-3">
          <Button type="button" disabled={action.busy || problems.length > 0} onClick={save}>
            Save schedule
          </Button>
          {saved && (
            <span className="flex items-center gap-1 text-sm font-medium text-success">
              <CheckIcon className="size-4" aria-hidden="true" />
              Saved.
            </span>
          )}
        </div>
      )}
      </CardContent>
    </Card>
  );
}

function DoctorRow({ doctor, canEdit, selected, onSelect, onChanged }: {
  doctor: Doctor;
  canEdit: boolean;
  selected: boolean;
  onSelect: () => void;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(doctor.display_name);
  const [tag, setTag] = useState(doctor.remark_tag ?? "");
  const action = useAction();

  async function save(e: FormEvent) {
    e.preventDefault();
    const ok = await action.run(() =>
      api.settings.updateDoctor(doctor.id, { display_name: name.trim(), remark_tag: tag.trim() || null }),
    );
    if (ok) {
      setEditing(false);
      onChanged();
    }
  }

  async function toggleActive() {
    const question = doctor.active
      ? `Mark ${doctor.display_name} as inactive (left the clinic)?`
      : `Mark ${doctor.display_name} as active again?`;
    if (window.confirm(question) && (await action.run(() => api.settings.updateDoctor(doctor.id, { active: !doctor.active })))) {
      onChanged();
    }
  }

  return (
    <TableRow data-state={selected ? "selected" : undefined} className={cn(!doctor.active && "text-muted-foreground", selected && "bg-brand-soft/60 hover:bg-brand-soft/60")}>
      <TableCell><strong className="font-semibold">{doctor.id}</strong></TableCell>
      {editing ? (
        <TableCell colSpan={2}>
          <form className="flex flex-wrap items-center gap-2" onSubmit={save}>
            <Input aria-label="Display name" value={name} onChange={(e) => setName(e.target.value)} required className="w-48" />
            <Input aria-label="Remark tag" value={tag} onChange={(e) => setTag(e.target.value)} size={4} maxLength={5} className="w-20" />
            <Button type="submit" size="sm" disabled={action.busy}>Save</Button>
            <Button type="button" size="sm" variant="outline" onClick={() => setEditing(false)}>Cancel</Button>
          </form>
          <ErrorBox message={action.error} />
        </TableCell>
      ) : (
        <>
          <TableCell>{doctor.display_name}</TableCell>
          <TableCell>{doctor.remark_tag}</TableCell>
        </>
      )}
      <TableCell>{doctor.active ? <Badge kind="ok">Active</Badge> : <Badge kind="closed">Inactive</Badge>}</TableCell>
      <TableCell className="text-right">
        <div className="flex justify-end gap-1.5 whitespace-nowrap">
          <Button type="button" size="sm" variant={selected ? "secondary" : "outline"} onClick={onSelect} disabled={selected}>
            {selected ? "Schedule shown" : "Schedule"}
          </Button>
          {canEdit && !editing && (
            <>
              <Button type="button" size="sm" variant="outline" onClick={() => setEditing(true)}>Edit</Button>
              <Button type="button" size="sm" variant={doctor.active ? "ghost-destructive" : "outline"} onClick={toggleActive} disabled={action.busy}>
                {doctor.active ? "Deactivate" : "Activate"}
              </Button>
            </>
          )}
        </div>
        {!editing && <ErrorBox message={action.error} />}
      </TableCell>
    </TableRow>
  );
}

function AddDoctorForm({ onAdded }: { onAdded: (id: string) => void }) {
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [tag, setTag] = useState("");
  const action = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ok = await action.run(async () => {
      const d = await api.explainDuplicate(
        api.settings.addDoctor({ id: id.trim(), display_name: name.trim(), remark_tag: tag.trim() || null }),
        "A doctor with this ID already exists.",
      );
      onAdded(d.id);
    });
    if (ok) {
      setId("");
      setName("");
      setTag("");
    }
  }

  return (
    <Card>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <SectionTitle title="Add a doctor">
            The new doctor starts with every day off. Set the working days in the schedule.
          </SectionTitle>
          <div className="grid items-end gap-4 sm:grid-cols-3">
            <Field label="GPiS DoctorID">
              <Input value={id} onChange={(e) => setId(e.target.value.toUpperCase())} required maxLength={20} />
            </Field>
            <Field label="Display name">
              <Input value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} />
            </Field>
            <Field label="Remark tag (e.g. P)">
              <Input value={tag} onChange={(e) => setTag(e.target.value)} maxLength={5} size={4} />
            </Field>
          </div>
          <ErrorBox message={action.error} />
          <div>
            <Button type="submit" disabled={action.busy}>Add doctor</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export default function DoctorsSection({ canEdit }: { canEdit: boolean }) {
  const doctors = useLoad(() => api.settings.doctors(), []);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const list = doctors.data ?? [];
  const selected = list.find((d) => d.id === selectedId) ?? list.find((d) => d.active) ?? null;

  return (
    <section className="flex flex-col gap-4">
      <ErrorBox message={doctors.error} onRetry={doctors.reload} />
      {doctors.data === undefined ? (
        doctors.loading && <Loading />
      ) : list.length === 0 ? (
        <Empty>No doctors yet.</Empty>
      ) : (
        <Card className="gap-0 overflow-hidden py-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>ID</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Remark tag</TableHead>
                <TableHead>Status</TableHead>
                <TableHead aria-label="Actions"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((d) => (
                <DoctorRow key={`${d.id}-${d.display_name}-${d.remark_tag}-${d.active}`} doctor={d} canEdit={canEdit}
                  selected={d.id === selected?.id} onSelect={() => setSelectedId(d.id)} onChanged={doctors.reload} />
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
      {selected && <ScheduleEditor key={selected.id} doctor={selected} canEdit={canEdit} />}
      {canEdit && (
        <AddDoctorForm
          onAdded={(id) => {
            setSelectedId(id);
            doctors.reload();
          }}
        />
      )}
    </section>
  );
}
