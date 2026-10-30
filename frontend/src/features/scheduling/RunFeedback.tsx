"use client";
import {
  CheckCircle2,
  RefreshCw,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";
import { useI18n } from "../../i18n/context";

interface Props {
  status?: string;
  hasRun: boolean;
  restoring: boolean;
  submitting: boolean;
  progress: number;
  candidateCount: number;
  error?: string | null;
  onReview: () => void;
  onRetry: () => void;
  retryDisabled: boolean;
  onReviewSource?: () => void;
  attemptFailed?: boolean;
}
export function RunFeedback({
  status,
  hasRun,
  restoring,
  submitting,
  progress,
  candidateCount,
  error,
  onReview,
  onRetry,
  retryDisabled,
  onReviewSource,
  attemptFailed = false,
}: Props) {
  const { locale } = useI18n(),
    el = locale === "el";
  if (!hasRun && !submitting) return null;
  const running = ["queued", "claimed", "running"].includes(status ?? "");
  const stopped = ["failed", "cancelled"].includes(status ?? "");
  const ready = !submitting && !restoring && candidateCount > 0 && !running;
  const reviewLabel =
    candidateCount === 1
      ? el
        ? "Έλεγχος πρότασης"
        : "Review proposal"
      : el
        ? "Έλεγχος προτάσεων"
        : "Review proposals";
  let title = "",
    description = "";
  if (submitting) {
    title = el ? "Αποστολή αιτήματος…" : "Submitting your request…";
    description = el
      ? "Το αποθηκευμένο πρόγραμμά σας παραμένει ως έχει."
      : "Your saved schedule stays as it is.";
  } else if (restoring) {
    title = el ? "Έλεγχος αποθηκευμένης αναζήτησης…" : "Checking saved search…";
    description = error
      ? el
        ? "Δεν ήταν δυνατός ο έλεγχος. Γίνεται επανασύνδεση· μπορείτε να συνεχίσετε σε άλλη σελίδα."
        : "The saved search could not be checked. Reconnecting; you can work on another page."
      : el
        ? "Ανάκτηση της πραγματικής κατάστασης και των διαθέσιμων προτάσεων."
        : "Retrieving the actual status and available proposals.";
  } else if (running) {
    title =
      status === "queued"
        ? el
          ? "Σε αναμονή για έναρξη"
          : "Waiting to start"
        : status === "claimed"
          ? el
            ? "Η αναζήτηση ξεκινά"
            : "Starting search"
          : el
            ? "Αναζήτηση αναθέσεων"
            : "Finding assignments";
    description = error
      ? el
        ? "Η σύνδεση διακόπηκε. Γίνεται επανασύνδεση· η πρόοδος είναι η τελευταία επιβεβαιωμένη."
        : "Connection interrupted. Reconnecting; progress is the last confirmed value."
      : el
        ? "Μπορείτε να συνεχίσετε σε άλλη σελίδα. Η αναζήτηση εκτελείται στο παρασκήνιο."
        : "You can work on another page. The search runs in the background.";
  } else if (ready) {
    title = attemptFailed
      ? el
        ? "Η προηγούμενη πρόταση παραμένει διαθέσιμη."
        : "Your previous proposal remains available."
      : stopped
        ? el
          ? "Η αναζήτηση σταμάτησε· υπάρχουν ενδιάμεσες προτάσεις"
          : "Search stopped; intermediate proposals are available"
        : el
          ? "Η πρόταση είναι έτοιμη για έλεγχο."
          : "Your proposal is ready to review.";
    description = el
      ? "Ελέγξτε τις αναθέσεις και τα ευρήματα. Η εφαρμογή στο προσχέδιο και η δημοσίευση είναι ξεχωριστά βήματα."
      : "Review assignments and findings. Applying a proposal and publishing a schedule are separate steps.";
  } else if (stopped || status === "unavailable") {
    title = el ? "Η αναζήτηση δεν ολοκληρώθηκε." : "The search did not finish.";
    description = el
      ? "Οι αποθηκευμένες αναθέσεις σας δεν άλλαξαν. Ελέγξτε τα στοιχεία ή δοκιμάστε ξανά."
      : "Your saved assignments are unchanged. Review the inputs or try again.";
  } else if (status === "completed") {
    title = el
      ? "Η αναζήτηση ολοκληρώθηκε χωρίς πρόταση."
      : "The search finished without a proposal.";
    description = el
      ? "Ελέγξτε την προετοιμασία της ημέρας και δοκιμάστε ξανά."
      : "Review the service-day preparation and try again.";
  } else {
    title = el ? "Έλεγχος κατάστασης…" : "Checking search status…";
    description = error
      ? el
        ? "Δεν ήταν δυνατή η ανάκτηση. Οι αποθηκευμένες αλλαγές παραμένουν ασφαλείς."
        : "The status could not be retrieved. Your saved changes remain intact."
      : "";
  }
  return (
    <section
      className={`run-feedback ${ready ? "ready" : stopped ? "stopped" : ""}`}
      aria-label={el ? "Κατάσταση αναζήτησης" : "Search status"}
    >
      <div className="run-feedback-copy" role="status">
        {ready ? (
          <CheckCircle2 size={21} />
        ) : stopped ? (
          <AlertTriangle size={21} />
        ) : (
          <RefreshCw
            className={running || submitting || restoring ? "spin" : ""}
            size={20}
          />
        )}
        <div>
          <strong>{title}</strong>
          <p>{description}</p>
        </div>
      </div>
      {running && !restoring && !submitting && (
        <div className="job-progress">
          <progress value={Math.max(0, Math.min(100, progress))} max={100} />
          <strong>{Math.round(progress)}%</strong>
        </div>
      )}
      {!submitting && !restoring && (
        <div className="run-feedback-actions">
          {candidateCount > 0 && (
            <button className="button primary" onClick={onReview}>
              {reviewLabel}
              <ArrowRight size={15} />
            </button>
          )}
          {!running &&
            (stopped ||
              status === "unavailable" ||
              (status === "completed" && candidateCount === 0)) && (
              <>
                <button
                  className="button secondary"
                  onClick={onRetry}
                  disabled={retryDisabled}
                >
                  {el ? "Νέα προσπάθεια" : "Try again"}
                </button>
                {onReviewSource && (
                  <button className="button secondary" onClick={onReviewSource}>
                    {el ? "Έλεγχος ημέρας" : "Review service day"}
                  </button>
                )}
              </>
            )}
        </div>
      )}
      {error && !submitting && !restoring && (
        <details className="run-feedback-details">
          <summary>
            {el ? "Περισσότερες πληροφορίες" : "More information"}
          </summary>
          <p>{error}</p>
        </details>
      )}
    </section>
  );
}
