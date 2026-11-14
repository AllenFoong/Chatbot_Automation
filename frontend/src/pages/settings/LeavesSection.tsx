// 医生请假（备用，W25）：本系统记录的请假日，那天这位医生没有空档。
// GPiS 里的 OFF DAY 记录本来就会被检查，这里是给没写进 GPiS 的请假用的。

import { useState, type FormEvent } from "react";
import * as api from "../../api";
import { Empty, ErrorBox, Field, Loading, SectionTitle } from "../../components";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { NativeSelect } from "../../components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import { clinicToday, formatDate } from "../../format";
import { useAction, useLoad } from "../../hooks";
import type { Doctor } from "../../types";

function AddLeaveForm({ doctors, onAdded }: { doctors: Doctor[]; onAdded: () => void }) {
  const [doctorId, setDoctorId] = useState("");
  const [date, setDate] = useState("");
  const [reason, setReason] = useState("");
  const action = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ok = await action.run(() =>
      api.explainDuplicate(
        api.settings.addLeave({ doctor_id: doctorId, leave_date: date, reason: reason.trim() || null }),
        "This doctor already has leave on this date.",
      ),
    );
    if (ok) {
      setDate("");
      setReason("");
      onAdded();
    }
  }

  return (
    <Card>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <SectionTitle title="Add doctor leave">Only for leave that is not written in GPiS as an OFF DAY.</SectionTitle>
          <div className="grid items-end gap-4 sm:grid-cols-3">
            <Field label="Doctor">
              <NativeSelect value={doctorId} onChange={(e) => setDoctorId(e.target.value)} required>
                <option value="">Choose…</option>
                {doctors.filter((d) => d.active).map((d) => (
                  <option key={d.id} value={d.id}>{d.display_name}</option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Date">
              <Input type="date" value={date} min={clinicToday()} onChange={(e) => setDate(e.target.value)} required />
            </Field>
            <Field label="Reason (optional)">
              <Input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={100} />
            </Field>
          </div>
          <ErrorBox message={action.error} />
          <div>
            <Button type="submit" disabled={action.busy}>Add leave</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export default function LeavesSection({ canEdit }: { canEdit: boolean }) {
  const leaves = useLoad(() => api.settings.leaves(), []);
  const doctors = useLoad(() => api.settings.doctors(), []);
  const action = useAction();
  const names = new Map((doctors.data ?? []).map((d) => [d.id, d.display_name]));

  async function remove(doctorId: string, date: string) {
    if (window.confirm(`Delete the leave of ${names.get(doctorId) ?? doctorId} on ${formatDate(date)}?`)) {
      if (await action.run(() => api.settings.deleteLeave(doctorId, date))) leaves.reload();
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <p className="max-w-[80ch] text-sm text-muted-foreground">
        Leave from today onwards. A doctor on leave has no free slots that day. "OFF DAY" records in GPiS are
        also respected, so this list is only for leave that is not in GPiS.
      </p>
      <ErrorBox message={action.error} />
      <ErrorBox message={leaves.error ?? doctors.error} onRetry={leaves.reload} />
      {leaves.data === undefined ? (
        leaves.loading && <Loading />
      ) : leaves.data.length === 0 ? (
        <Empty>No upcoming doctor leave.</Empty>
      ) : (
        <Card className="gap-0 overflow-hidden py-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Date</TableHead>
                <TableHead>Doctor</TableHead>
                <TableHead>Reason</TableHead>
                {canEdit && <TableHead aria-label="Actions"></TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {leaves.data.map((l) => (
                <TableRow key={`${l.doctor_id}-${l.leave_date}`}>
                  <TableCell className="whitespace-nowrap">{formatDate(l.leave_date)}</TableCell>
                  <TableCell>{names.get(l.doctor_id) ?? l.doctor_id}</TableCell>
                  <TableCell>{l.reason}</TableCell>
                  {canEdit && (
                    <TableCell className="text-right">
                      <Button type="button" size="sm" variant="ghost-destructive" disabled={action.busy} onClick={() => remove(l.doctor_id, l.leave_date)}>
                        Delete
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
      {canEdit && doctors.data && <AddLeaveForm doctors={doctors.data} onAdded={leaves.reload} />}
    </section>
  );
}
