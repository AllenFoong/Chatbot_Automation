// 假期管理（D14、D27）：诊所整天休息的日子。
// - 一键预填一年的全国 + Johor 公共假期（只加没有的日子）
// - 农历新年多休的日子、诊所自己定的休息日，要员工自己加
// - 回教节日是预估日期，导入后要核对

import { useState, type FormEvent } from "react";
import * as api from "../../api";
import { Empty, ErrorBox, Field, Loading, Notice, SectionTitle } from "../../components";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import { clinicToday, formatDate } from "../../format";
import { useAction, useLoad } from "../../hooks";
import { ChevronLeftIcon, ChevronRightIcon, DownloadIcon } from "../../icons";

function AddClosureForm({ year, onAdded }: { year: number; onAdded: () => void }) {
  const [date, setDate] = useState("");
  const [reason, setReason] = useState("");
  const action = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (await action.run(() => api.explainDuplicate(
          api.settings.addClosure({ closure_date: date, reason: reason.trim() }),
          "This date is already a closure day.",
        ))) {
      setDate("");
      setReason("");
      onAdded();
    }
  }

  return (
    <Card>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <SectionTitle title="Add a closure day">
            For example a day the clinic decides to close. No new bookings on that day; appointments already there
            show under <em>Needs staff</em> on the Reminders page, so you can tell the patients.
          </SectionTitle>
          <div className="grid items-end gap-4 sm:grid-cols-[200px_1fr]">
            <Field label="Date">
              <Input type="date" value={date} min={`${year - 1}-01-01`} onChange={(e) => setDate(e.target.value)} required />
            </Field>
            <Field label="Reason">
              <Input value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={100} />
            </Field>
          </div>
          <ErrorBox message={action.error} />
          <div>
            <Button type="submit" disabled={action.busy}>Add</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export default function ClosuresSection({ canEdit }: { canEdit: boolean }) {
  const [year, setYear] = useState(() => Number(clinicToday().slice(0, 4)));
  const closures = useLoad(() => api.settings.closures(year), [year]);
  const action = useAction();
  const [imported, setImported] = useState<string | null>(null);

  async function importHolidays() {
    setImported(null);
    if (
      !window.confirm(
        `Add the public holidays the clinic closes on in ${year}? ` +
          "(New Year's Day, Chinese New Year 2 days, Hari Raya Aidilfitri 2 days, Sultan of Johor's Birthday, Labour Day, " +
          "Merdeka Day, Malaysia Day, Deepavali, Christmas Day. Replacement days are not added.) " +
          "Days already in the list are kept.",
      )
    )
      return;
    await action.run(async () => {
      const result = await api.settings.importHolidays(year);
      setImported(
        `Added ${result.added.length} day(s); ${result.already_there} were already there. ` +
          "Please check the Hari Raya dates (they are estimates) and add any other day the clinic closes.",
      );
      closures.reload();
    });
  }

  async function remove(date: string, reason: string) {
    if (window.confirm(`Delete the closure on ${formatDate(date)} (${reason})?`)) {
      if (await action.run(() => api.settings.deleteClosure(date))) closures.reload();
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="icon" onClick={() => setYear((y) => y - 1)} aria-label="Previous year">
            <ChevronLeftIcon />
          </Button>
          <h2 className="w-16 text-center text-xl font-semibold tabular-nums">{year}</h2>
          <Button type="button" variant="outline" size="icon" onClick={() => setYear((y) => y + 1)} aria-label="Next year">
            <ChevronRightIcon />
          </Button>
        </div>
        {canEdit && (
          <Button type="button" variant="outline" disabled={action.busy} onClick={importHolidays}>
            <DownloadIcon />
            Import public holidays for {year}
          </Button>
        )}
      </div>
      {imported && <Notice tone="success">{imported}</Notice>}
      <ErrorBox message={action.error} />
      <ErrorBox message={closures.error} onRetry={closures.reload} />
      {closures.data === undefined ? (
        closures.loading && <Loading />
      ) : closures.data.length === 0 ? (
        <Empty>No closure days in {year}. The clinic is treated as open every day.</Empty>
      ) : (
        <Card className="gap-0 overflow-hidden py-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Date</TableHead>
                <TableHead>Reason</TableHead>
                {canEdit && <TableHead aria-label="Actions"></TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {closures.data.map((c) => (
                <TableRow key={c.closure_date}>
                  <TableCell className="whitespace-nowrap">{formatDate(c.closure_date)}</TableCell>
                  <TableCell>{c.reason}</TableCell>
                  {canEdit && (
                    <TableCell className="text-right">
                      <Button type="button" size="sm" variant="ghost-destructive" disabled={action.busy} onClick={() => remove(c.closure_date, c.reason)}>
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
      {canEdit && <AddClosureForm year={year} onAdded={closures.reload} />}
    </section>
  );
}
