"use client";

import React, { useState } from "react";
import { useI18n } from "../../i18n/context";

interface IncidentReporterProps {
  onClose: () => void;
  onSubmitIncident: (incident: {
    type: string;
    resourceId?: string;
    tripId?: string;
    description: string;
  }) => Promise<void>;
}

export function IncidentReporter({ onClose, onSubmitIncident }: IncidentReporterProps) {
  const { locale } = useI18n();
  const isEl = locale === "el";

  const [type, setType] = useState<string>("VEHICLE_BREAKDOWN");
  const [resourceId, setResourceId] = useState<string>("");
  const [tripId, setTripId] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim()) return;

    setIsSubmitting(true);
    try {
      await onSubmitIncident({
        type,
        resourceId: resourceId.trim() || undefined,
        tripId: tripId.trim() || undefined,
        description: description.trim(),
      });
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-lg max-w-md w-full shadow-xl overflow-hidden">
        <div className="p-4 bg-muted/40 border-b border-border flex items-center justify-between">
          <h3 className="font-bold text-sm text-foreground">
            {isEl ? "Αναφορά Επιχειρησιακού Συμβάντος" : "Report Operational Incident"}
          </h3>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground text-sm font-bold"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-3.5 text-xs">
          <div>
            <label className="block font-medium text-muted-foreground mb-1">
              {isEl ? "Τύπος Περιστατικού" : "Incident Type"}
            </label>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="w-full p-2 rounded border border-border bg-background text-foreground focus:outline-none"
            >
              <option value="VEHICLE_BREAKDOWN">{isEl ? "Βλάβη Οχήματος / Λεωφορείου" : "Vehicle Breakdown"}</option>
              <option value="DRIVER_SICK_LEAVE">{isEl ? "Αιφνίδια Ασθένεια Οδηγού" : "Driver Illness"}</option>
              <option value="ROUTE_BLOCKAGE">{isEl ? "Κλείσιμο Δρόμου / Καθυστέρηση" : "Road Blockage / Delay"}</option>
              <option value="OTHER">{isEl ? "Άλλο Συμβάν" : "Other"}</option>
            </select>
          </div>

          <div>
            <label className="block font-medium text-muted-foreground mb-1">
              {isEl ? "Αριθμός Κυκλοφορίας / Πόρος (προαιρετικό)" : "Bus Plate / Resource (optional)"}
            </label>
            <input
              type="text"
              value={resourceId}
              onChange={(e) => setResourceId(e.target.value)}
              placeholder="π.χ. AXA-1234"
              className="w-full p-2 rounded border border-border bg-background text-foreground focus:outline-none"
            />
          </div>

          <div>
            <label className="block font-medium text-muted-foreground mb-1">
              {isEl ? "Κωδικός Δρομολογίου (προαιρετικό)" : "Trip Code (optional)"}
            </label>
            <input
              type="text"
              value={tripId}
              onChange={(e) => setTripId(e.target.value)}
              placeholder="π.χ. TRIP-102"
              className="w-full p-2 rounded border border-border bg-background text-foreground focus:outline-none"
            />
          </div>

          <div>
            <label className="block font-medium text-muted-foreground mb-1">
              {isEl ? "Περιγραφή & Σημειώσεις" : "Description & Notes"} *
            </label>
            <textarea
              required
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={isEl ? "Περιγράψτε το συμβάν και τις επείγουσες ανάγκες..." : "Describe the breakdown or disruption..."}
              className="w-full p-2 rounded border border-border bg-background text-foreground focus:outline-none"
            />
          </div>

          <div className="pt-2 flex items-center justify-end gap-2 border-t border-border">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 rounded border border-border text-muted-foreground hover:bg-muted"
            >
              {isEl ? "Ακύρωση" : "Cancel"}
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-1.5 rounded bg-red-600 text-white font-semibold hover:bg-red-500 disabled:opacity-50"
            >
              {isSubmitting ? (isEl ? "Υποβολή..." : "Submitting...") : (isEl ? "Υποβολή Συμβάντος" : "Submit Incident")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
