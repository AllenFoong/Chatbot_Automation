// 价目表（W64、D82）：AI 回答价钱照这里写的；ADMIN 改，STAFF 只能看。清空 = 问价钱一律转员工。
// 只送 price_info，不会动到 Slots & auto-confirm 的设定。

import { useEffect, useState, type FormEvent } from "react";
import * as api from "../../api";
import { ErrorBox, Loading } from "../../components";
import { useAction, useLoad } from "../../hooks";

export default function PricesSection({ canEdit }: { canEdit: boolean }) {
  const settings = useLoad(() => api.settings.clinic(), []);
  const [text, setText] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const action = useAction();

  useEffect(() => {
    if (settings.data) setText(settings.data.price_info ?? "");
  }, [settings.data]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (text === null) return;
    let result: string | null = null;
    if (await action.run(async () => (result = (await api.settings.updateClinic({ price_info: text })).price_info))) {
      setText(result ?? "");
      setSaved(true);
    }
  }

  if (text === null) {
    return (
      <>
        <ErrorBox message={settings.error} onRetry={settings.reload} />
        {settings.loading && <Loading />}
      </>
    );
  }

  return (
    <form className="card inline-form settings-form" onSubmit={submit}>
      <div className="card-title">
        <h3>Price list for the AI</h3>
        <p>
          The AI answers price questions only from this text, in the patient's language. Anything not written here
          goes to staff. Leave it empty to send every price question to staff.
        </p>
      </div>
      <label>
        Prices (RM)
        <textarea
          className="price-info"
          rows={24}
          maxLength={10000}
          value={text}
          readOnly={!canEdit}
          onChange={(e) => {
            setSaved(false);
            setText(e.target.value);
          }}
        />
      </label>
      <p className="help">Write it in English; one treatment per line. Ranges are fine: the AI says the doctor confirms the price.</p>

      <ErrorBox message={action.error} />
      {canEdit && (
        <div className="actions">
          <button type="submit" className="primary" disabled={action.busy}>Save</button>
          {saved && <span className="ok">Saved.</span>}
        </div>
      )}
    </form>
  );
}
