"use client";
import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../../i18n/context";
import { useUnsavedChanges } from "../navigation/use-unsaved-changes";
import { RouteList } from "./RouteList";
import { WorkRulesError, put, recordCall, type RouteOption } from "./workrules-api";

interface View {
  vehicle_id: number;
  route_ids: number[];
}

export function VehicleRouteRules({ vehicleId, onDirty }: { vehicleId: number; onDirty: (dirty: boolean) => void }) {
  const { apiFetch, user } = useAuth(),
    el = useI18n().locale === "el",
    canEdit = !!user?.permissions.includes("fleet.write");
  const [routes, setRoutes] = useState<RouteOption[]>([]),
    [saved, setSaved] = useState<number[] | null>(null),
    [ids, setIds] = useState<number[]>([]),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const base = `/vehicles/${vehicleId}/forbidden-routes`;
  useEffect(() => {
    const load = async () => {
      try {
        const [list, view] = await Promise.all([recordCall<{ routes: RouteOption[] }>(apiFetch, "/routes"), recordCall<View>(apiFetch, base)]);
        setRoutes(list.routes);
        setSaved(view.route_ids);
        setIds(view.route_ids);
      } catch {
        setError(el ? "Δεν φορτώθηκαν οι περιορισμοί γραμμών." : "The route restrictions could not be loaded.");
      }
    };
    void load();
  }, [apiFetch, base, el]);
  const dirty = saved !== null && ids.join() !== saved.join();
  useUnsavedChanges(dirty || busy);
  useEffect(() => onDirty(dirty), [dirty, onDirty]);
  async function save() {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const view = await put<View>(apiFetch, base, { route_ids: ids });
      setSaved(view.route_ids);
      setIds(view.route_ids);
      setNotice(el ? "Αποθηκεύτηκε." : "Saved.");
    } catch (failure) {
      setError(
        failure instanceof WorkRulesError && failure.code === "offline"
          ? el ? "Δεν υπάρχει σύνδεση. Δεν αποθηκεύτηκε τίποτα." : "No connection. Nothing was saved."
          : el ? "Η ενέργεια δεν ολοκληρώθηκε." : "The action could not be completed.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="office-panel" aria-label={el ? "Περιορισμοί γραμμών" : "Route restrictions"}>
      {error && <p className="auth-error" role="alert">{error}</p>}
      {notice && <p className="office-summary" role="status">{notice}</p>}
      <RouteList
        title={el ? "Δεν επιτρέπεται" : "Not allowed"}
        addLabel={el ? "Προσθήκη απαγορευμένης γραμμής" : "Add a forbidden route"}
        selected={ids}
        routes={routes}
        disabled={!canEdit || busy || saved === null}
        el={el}
        onChange={setIds}
      />
      {canEdit && (
        <button type="button" className="button primary" disabled={!dirty || busy} onClick={() => void save()}>
          {el ? "Αποθήκευση περιορισμών γραμμών" : "Save route restrictions"}
        </button>
      )}
    </section>
  );
}
