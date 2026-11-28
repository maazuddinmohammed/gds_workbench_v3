// A plain table of records (the shape core/parts.py gives every part), with a filter box, optional row selection and
// a link on each row. Used by every step page.

import { useState } from "react";

export type Row = Record<string, unknown>;

type Props = {
  rows: Row[];
  columns: string[];
  labels?: Record<string, string>;
  rowKey: (row: Row) => string;
  selected?: Set<string>;
  onSelect?: (selected: Set<string>) => void;
  onOpen?: (row: Row) => void;
  empty?: string;
};

export function show(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (value === true) return "✓";
  if (value === false) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function Records({ rows, columns, labels, rowKey, selected, onSelect, onOpen, empty }: Props) {
  const [filter, setFilter] = useState("");
  const shown = filter
    ? rows.filter((r) => columns.some((c) => show(r[c]).toLowerCase().includes(filter.toLowerCase())))
    : rows;
  const toggle = (key: string) => {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onSelect?.(next);
  };
  return (
    <div className="records">
      <div className="records-bar">
        <input placeholder="Filter" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <span className="muted">
          {shown.length} of {rows.length}
        </span>
        {onSelect && selected && selected.size > 0 && (
          <button onClick={() => onSelect(new Set())}>Clear {selected.size} picked</button>
        )}
      </div>
      {rows.length === 0 ? (
        <p className="muted">{empty ?? "Nothing yet."}</p>
      ) : (
        <table>
          <thead>
            <tr>
              {onSelect && (
                <th>
                  <input
                    type="checkbox"
                    checked={shown.length > 0 && shown.every((r) => selected?.has(rowKey(r)))}
                    onChange={(e) => onSelect(new Set(e.target.checked ? shown.map(rowKey) : []))}
                  />
                </th>
              )}
              {columns.map((c) => (
                <th key={c}>{labels?.[c] ?? c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => {
              const key = rowKey(row);
              return (
                <tr key={key} className={row.is_active === false ? "off" : ""}>
                  {onSelect && (
                    <td>
                      <input type="checkbox" checked={selected?.has(key) ?? false} onChange={() => toggle(key)} />
                    </td>
                  )}
                  {columns.map((c, i) => (
                    <td key={c} title={show(row[c])} className={typeof row[c] === "string" && show(row[c]).length > 80 ? "long" : ""}>
                      {i === 0 && onOpen ? <a onClick={() => onOpen(row)}>{show(row[c])}</a> : show(row[c])}
                      {i === 0 && row.is_locked === true && <span className="tag">locked</span>}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
