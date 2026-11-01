type PendingEdit = () => { dirty: boolean; message: string };
const pending = new Set<PendingEdit>();
export function registerPendingEdit(value: PendingEdit) {
  pending.add(value);
  return () => {
    pending.delete(value);
  };
}
export function hasPendingEdits() {
  return [...pending].some((value) => value().dirty);
}
export function mayLeaveWorkspace() {
  const edit = [...pending]
    .map((value) => value())
    .find((value) => value.dirty);
  return !edit || window.confirm(edit.message);
}

export function confirmDiscardOwn(dirty: boolean, isEl: boolean) {
  return !dirty || window.confirm(isEl
    ? "Έχετε μη αποθηκευμένες αλλαγές. Θέλετε να φύγετε και να τις απορρίψετε;"
    : "You have unsaved changes. Leave and discard them?");
}
