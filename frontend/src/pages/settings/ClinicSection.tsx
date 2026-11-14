// 每格上限（W22、D15）、GPiS 里诊所自己的 ContactID（统计 B6）、自动确认的开关（D71 ②，只有 ADMIN 能改）。
// 数据库只接受 1–3（D19），画面也只给 1–3 选。

import { useEffect, useState, type FormEvent } from "react";
import * as api from "../../api";
import { CheckIcon } from "lucide-react";
import { ErrorBox, Field, Loading, SectionTitle, Switch } from "../../components";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { NativeSelect } from "../../components/ui/native-select";
import { Separator } from "../../components/ui/separator";
import { useAction, useLoad } from "../../hooks";
import type { ClinicSettings } from "../../types";

export default function ClinicSection({ canEdit }: { canEdit: boolean }) {
  const settings = useLoad(() => api.settings.clinic(), []);
  const [form, setForm] = useState<ClinicSettings | null>(null);
  const [stored, setStored] = useState<ClinicSettings | null>(null); // 数据库里现在的设定（拨了还没 Save 的要提醒）
  const [saved, setSaved] = useState(false);
  const action = useAction();

  useEffect(() => {
    if (settings.data) {
      setForm(settings.data);
      setStored(settings.data);
    }
  }, [settings.data]);

  function change(patch: Partial<ClinicSettings>) {
    setSaved(false);
    setForm((f) => (f ? { ...f, ...patch } : f));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    let result: ClinicSettings | undefined;
    if (await action.run(async () => (result = await api.settings.updateClinic(form)))) {
      setForm(result!);
      setStored(result!);
      setSaved(true);
    }
  }

  if (!form) {
    return (
      <>
        <ErrorBox message={settings.error} onRetry={settings.reload} />
        {settings.loading && <Loading />}
      </>
    );
  }

  const choices = [1, 2, 3];
  return (
    <Card className="max-w-2xl">
      <CardContent>
        <form className="flex flex-col gap-5" onSubmit={submit}>
          <SectionTitle title="Slot limits">
            How many patients can share one 30-minute slot, and the clinic's own contact in GPiS.
          </SectionTitle>
          <Field
            label="Patients per slot (at most)"
            help={'The 3rd place is only for short treatments ("Can be 3rd") and only when the slots next to it are not full.'}
          >
            <NativeSelect value={form.max_per_slot} disabled={!canEdit} onChange={(e) => change({ max_per_slot: Number(e.target.value) })} className="max-w-40">
              {choices.map((n) => <option key={n} value={n}>{n}</option>)}
            </NativeSelect>
          </Field>

          <Field label="Patients per slot the AI may book (at most)" help="Set to 2 to keep the 3rd place for staff only.">
            <NativeSelect value={form.max_per_slot_for_ai} disabled={!canEdit} onChange={(e) => change({ max_per_slot_for_ai: Number(e.target.value) })} className="max-w-40">
              {choices.map((n) => <option key={n} value={n}>{n}</option>)}
            </NativeSelect>
          </Field>

          <Field
            label="Clinic's own ContactID in GPiS"
            help="Appointments under this contact (other than OFF DAY) mark the day for staff review."
          >
            <Input type="number" min={1} value={form.clinic_contact_id} disabled={!canEdit} className="max-w-40"
              onChange={(e) => change({ clinic_contact_id: Number(e.target.value) })} required />
          </Field>

          <Separator />

          <SectionTitle title="Auto-confirm from GPiS">
            Every 3 minutes (9:00–17:30) the system looks in GPiS for the appointments staff entered. A request is
            confirmed and the patient is messaged only when GPiS has exactly the same patient, date, time, doctor,
            treatment and length. Everything else still waits for <em>Entered in GPiS</em>.
          </SectionTitle>
          <Switch
            label="Confirm matching requests automatically"
            checked={form.auto_confirm}
            disabled={!canEdit}
            onChange={(on) => change({ auto_confirm: on })}
          />
          {/* 关的时候不写说明（开发者 2026-10-18 要的）；拨了还没 Save 的才写 Press Save to apply. */}
          {form.auto_confirm && (
            <p className="-mt-2 text-xs text-muted-foreground">
              Off by default. Turn it on after staff have used Entered in GPiS for a while and the requests match GPiS.
              New patients are never confirmed automatically the first time.
            </p>
          )}
          {canEdit && stored && form.auto_confirm !== stored.auto_confirm && (
            <p className="-mt-2 text-xs font-medium text-warning">Press Save to apply.</p>
          )}

          <ErrorBox message={action.error} />
          {canEdit && (
            <div className="flex items-center gap-3">
              <Button type="submit" disabled={action.busy}>Save</Button>
              {saved && (
                <span className="flex items-center gap-1 text-sm font-medium text-success">
                  <CheckIcon className="size-4" aria-hidden="true" />
                  Saved.
                </span>
              )}
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
