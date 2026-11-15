"use client";
import { X } from "lucide-react";
import { routeName, type RouteOption } from "./workrules-api";

export function RouteList({
  title,
  addLabel,
  selected,
  routes,
  blocked = [],
  disabled,
  el,
  onChange,
}: {
  title: string;
  addLabel: string;
  selected: number[];
  routes: RouteOption[];
  blocked?: number[];
  disabled: boolean;
  el: boolean;
  onChange: (ids: number[]) => void;
}) {
  const byId = new Map(routes.map((r) => [r.id, r]));
  const free = routes.filter((r) => !selected.includes(r.id) && !blocked.includes(r.id));
  return (
    <div className="resource-field">
      <strong>{title}</strong>
      <ul className="office-chips">
        {selected.map((id) => {
          const name = byId.has(id) ? routeName(byId.get(id)!, el) : `#${id}`;
          return (
            <li key={id} className="status-pill neutral">
              {name}
              {!disabled && (
                <button type="button" className="icon-button" aria-label={`${el ? "Αφαίρεση" : "Remove"} ${name}`} onClick={() => onChange(selected.filter((x) => x !== id))}>
                  <X size={12} />
                </button>
              )}
            </li>
          );
        })}
        {!selected.length && <li>{el ? "Καμία" : "None"}</li>}
      </ul>
      {!disabled && (
        <select
          aria-label={addLabel}
          value=""
          onChange={(e) => e.target.value && onChange([...selected, Number(e.target.value)])}
        >
          <option value="">{el ? "+ Προσθήκη" : "+ Add"}</option>
          {free.map((r) => (
            <option key={r.id} value={r.id}>
              {routeName(r, el)}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
