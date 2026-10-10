import { useEffect, useState } from "react";
import { REFERENCE_CHECK_TIMEOUT_MS, referenceAvailabilityMessage, type ReferenceAvailability, type ReferenceChecker } from "@/lib/reference-availability";

export function ReferenceAvailabilityNotice({ url, check, busy, en }: {
  url: string; check: ReferenceChecker; busy: boolean; en: boolean;
}) {
  const [state, setState] = useState<ReferenceAvailability | "checking">("checking");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), REFERENCE_CHECK_TIMEOUT_MS);
    setState("checking");
    void check(url, controller.signal).then(result => { if (current) setState(result); })
      .catch(() => { if (current) setState("temporary_error"); })
      .finally(() => window.clearTimeout(timer));
    return () => { current = false; controller.abort(); window.clearTimeout(timer); };
  }, [url, check, revision]);
  return <div className="ux2-reference-availability" data-reference-availability={state}>
    <p role="status">{referenceAvailabilityMessage(state, en)}</p>
    {state !== "checking" && state !== "available" && <button type="button" className="apix-focus-ring" disabled={busy}
      onClick={() => setRevision(value => value + 1)}>{en ? "Check again" : "Проверить снова"}</button>}
  </div>;
}
