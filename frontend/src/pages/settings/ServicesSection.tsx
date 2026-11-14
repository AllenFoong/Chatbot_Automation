// 疗程代码（和 GPiS Remarks 同一套）。这些设定决定 AI 能不能自己约、能不能当一格的第 3 人（D15、D16）。
// 不再提供的疗程改成 inactive，不删除（旧的预约请求还会用到）。

import { useState, type FormEvent, type ReactNode } from "react";
import * as api from "../../api";
import { CheckIcon } from "lucide-react";
import { Badge, ErrorBox, Field, Loading, SectionTitle } from "../../components";
import { Badge as UiBadge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Checkbox } from "../../components/ui/checkbox";
import { Input } from "../../components/ui/input";
import { NativeSelect } from "../../components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import { cn } from "../../lib/utils";
import { useAction, useLoad } from "../../hooks";
import type { Service, ServiceIn } from "../../types";

// 多步骤疗程：后续预约要同一位医生（W9、D21、D33）。和 backend/app/db/seed.py 用的类别一样
const TREATMENT_GROUPS = ["IMPLANT", "DENTURE", "ORTHO", "RCT", "CROWN", "BRIDGE"];

const FLAGS = [
  { key: "ai_can_book", label: "AI can book", help: "The AI may suggest a time by itself. If not, the AI collects the request and passes it to staff." },
  { key: "can_be_third", label: "Can be 3rd", help: "May use the 3rd place in a slot (short treatments)." },
  { key: "may_need_1h", label: "May need 1 h", help: "Staff decide if it needs 1 hour, so the AI passes it to staff." },
] as const;

type Draft = ServiceIn & { active: boolean };

/** 勾选框和它的名字（点名字也会勾） */
function CheckLabel({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <label title={title} className="flex cursor-pointer items-center gap-2 text-sm whitespace-nowrap">
      {children}
    </label>
  );
}

function GroupSelect({ value, onChange, className }: { value: string | null; onChange: (v: string | null) => void; className?: string }) {
  // 数据库里有这里不认识的类别时也要显示出来，不能看起来像 "single visit"
  const groups = value && !TREATMENT_GROUPS.includes(value) ? [...TREATMENT_GROUPS, value] : TREATMENT_GROUPS;
  return (
    <NativeSelect aria-label="Treatment group" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)} className={className}>
      <option value="">— (single visit)</option>
      {groups.map((g) => (
        <option key={g} value={g}>{g}</option>
      ))}
    </NativeSelect>
  );
}

function ServiceRow({ service, canEdit, onChanged }: { service: Service; canEdit: boolean; onChanged: () => void }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const action = useAction();

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!draft) return;
    const { code: _code, ...changes } = draft;
    if (await action.run(() => api.settings.updateService(service.code, { ...changes, name: changes.name.trim() }))) {
      setDraft(null);
      onChanged();
    }
  }

  if (draft) {
    return (
      <TableRow className="bg-brand-soft/50 hover:bg-brand-soft/50">
        <TableCell><strong className="font-semibold">{service.code}</strong></TableCell>
        <TableCell colSpan={7}>
          <form className="flex flex-wrap items-center gap-x-4 gap-y-2" onSubmit={save}>
            <Input aria-label="Name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} required maxLength={100} className="w-56" />
            {FLAGS.map((f) => (
              <CheckLabel key={f.key} title={f.help}>
                <Checkbox checked={draft[f.key]} onChange={(e) => setDraft({ ...draft, [f.key]: e.target.checked })} />
                {f.label}
              </CheckLabel>
            ))}
            <GroupSelect value={draft.treatment_group} onChange={(v) => setDraft({ ...draft, treatment_group: v })} className="w-44" />
            <CheckLabel>
              <Checkbox checked={draft.active} onChange={(e) => setDraft({ ...draft, active: e.target.checked })} />
              Active
            </CheckLabel>
            <span className="flex gap-2">
              <Button type="submit" size="sm" disabled={action.busy}>Save</Button>
              <Button type="button" size="sm" variant="outline" onClick={() => setDraft(null)}>Cancel</Button>
            </span>
          </form>
          <ErrorBox message={action.error} />
        </TableCell>
      </TableRow>
    );
  }

  return (
    <TableRow className={cn(!service.active && "text-muted-foreground")}>
      <TableCell><strong className="font-semibold">{service.code}</strong></TableCell>
      <TableCell>{service.name}</TableCell>
      {FLAGS.map((f) => (
        <TableCell key={f.key} className="text-center">
          {service[f.key] && (
            <span title="Yes" className="inline-flex text-success">
              <CheckIcon className="size-4" />
            </span>
          )}
        </TableCell>
      ))}
      <TableCell>{service.treatment_group && <UiBadge variant="outline">{service.treatment_group}</UiBadge>}</TableCell>
      <TableCell>{service.active ? <Badge kind="ok">Active</Badge> : <Badge kind="closed">Inactive</Badge>}</TableCell>
      <TableCell className="text-right">
        {canEdit && (
          <Button type="button" size="sm" variant="outline" onClick={() => setDraft({ ...service })}>Edit</Button>
        )}
      </TableCell>
    </TableRow>
  );
}

const EMPTY: ServiceIn = { code: "", name: "", can_be_third: false, may_need_1h: false, ai_can_book: false, treatment_group: null };

function AddServiceForm({ onAdded }: { onAdded: () => void }) {
  const [form, setForm] = useState<ServiceIn>(EMPTY);
  const action = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ok = await action.run(() => api.explainDuplicate(
        api.settings.addService({ ...form, code: form.code.trim(), name: form.name.trim() }),
        "This treatment code already exists.",
      ));
    if (ok) {
      setForm(EMPTY);
      onAdded();
    }
  }

  return (
    <Card>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <SectionTitle title="Add a treatment">Use the same code staff write in GPiS Remarks.</SectionTitle>
          <div className="grid items-end gap-4 sm:grid-cols-[160px_1fr_220px]">
            <Field label="Code">
              <Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} required maxLength={20} size={8} />
            </Field>
            <Field label="Name">
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required maxLength={100} />
            </Field>
            <Field label="Group">
              <GroupSelect value={form.treatment_group} onChange={(v) => setForm({ ...form, treatment_group: v })} />
            </Field>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            {FLAGS.map((f) => (
              <CheckLabel key={f.key} title={f.help}>
                <Checkbox checked={form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.checked })} />
                {f.label}
              </CheckLabel>
            ))}
          </div>
          <ErrorBox message={action.error} />
          <div>
            <Button type="submit" disabled={action.busy}>Add treatment</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export default function ServicesSection({ canEdit }: { canEdit: boolean }) {
  const services = useLoad(() => api.settings.services(), []);

  return (
    <section className="flex flex-col gap-4">
      <ul className="m-0 flex list-none flex-col gap-1 p-0 text-sm text-muted-foreground">
        {FLAGS.map((f) => (
          <li key={f.key}><strong className="font-semibold text-foreground">{f.label}</strong>: {f.help}</li>
        ))}
        <li><strong className="font-semibold text-foreground">Group</strong>: multi-step treatment; follow-up visits must be with the same doctor.</li>
      </ul>
      <ErrorBox message={services.error} onRetry={services.reload} />
      {services.data === undefined ? (
        services.loading && <Loading />
      ) : (
        <Card className="gap-0 overflow-hidden py-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Code</TableHead>
                <TableHead>Name</TableHead>
                {FLAGS.map((f) => (
                  <TableHead key={f.key} className="text-center">{f.label}</TableHead>
                ))}
                <TableHead>Group</TableHead>
                <TableHead>Status</TableHead>
                <TableHead aria-label="Actions"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {services.data.map((s) => (
                <ServiceRow key={`${JSON.stringify(s)}`} service={s} canEdit={canEdit} onChanged={services.reload} />
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
      {canEdit && <AddServiceForm onAdded={services.reload} />}
    </section>
  );
}
