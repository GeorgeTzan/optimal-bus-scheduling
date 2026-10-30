"""Stable internal keys behind readable, localized template labels."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    key: str
    en: str
    el: str
    kind: str = "text"
    required: bool = False

    def label(self, locale):
        return self.el if locale == "el" else self.en


def C(key, en, el, kind="text", required=False):
    return Column(key, en, el, kind, required)


SHEETS = {
    "drivers": (
        "Drivers",
        "Οδηγοί",
        (
            C("code", "Staff reference", "Κωδικός οδηγού", "reference"),
            C("first_name", "First name", "Όνομα", required=True),
            C("last_name", "Last name", "Επώνυμο", required=True),
            C("phone", "Phone", "Τηλέφωνο", "phone"),
            C("license_number", "Licence number", "Αριθμός άδειας", "reference"),
            C("home_station", "Home station", "Έδρα"),
            C("is_active", "Active", "Ενεργό", "boolean"),
        ),
    ),
    "vehicles": (
        "Vehicles",
        "Οχήματα",
        (
            C("code", "Vehicle reference", "Κωδικός οχήματος", "reference"),
            C("registration_plate", "Registration", "Πινακίδα", "reference"),
            C("bus_type", "Vehicle category", "Κατηγορία οχήματος", "reference", True),
            C("capacity", "Seats", "Θέσεις", "integer"),
            C("home_station", "Home station", "Έδρα"),
            C("is_active", "Active", "Ενεργό", "boolean"),
        ),
    ),
    "stations": (
        "Stations",
        "Σταθμοί",
        (
            C("code", "Station reference", "Κωδικός σταθμού", "reference"),
            C("name_el", "Station name", "Όνομα σταθμού", required=True),
            C("name_en", "English name", "Αγγλική ονομασία"),
            C("is_depot", "Depot", "Αμαξοστάσιο", "boolean"),
            C("latitude", "Latitude", "Γεωγραφικό πλάτος", "decimal"),
            C("longitude", "Longitude", "Γεωγραφικό μήκος", "decimal"),
            C("is_active", "Active", "Ενεργό", "boolean"),
        ),
    ),
    "timetable": (
        "Timetable",
        "Δρομολόγια",
        (
            C("trip_code", "Trip reference", "Κωδικός δρομολογίου", "reference", True),
            C("origin", "Origin station", "Σταθμός αναχώρησης", required=True),
            C("destination", "Destination station", "Σταθμός άφιξης", required=True),
            C("departure_time", "Departure time", "Ώρα αναχώρησης", "clock", True),
            C("arrival_time", "Arrival time", "Ώρα άφιξης", "clock", True),
            C("arrival_day_offset", "Arrival day", "Ημέρα άφιξης", "arrival_day", True),
            C(
                "operating_weekdays",
                "Operating days",
                "Ημέρες λειτουργίας",
                "weekdays",
                True,
            ),
            C("valid_from", "Valid from", "Ισχύει από", "date", True),
            C("valid_until", "Valid until", "Ισχύει έως", "date", True),
            C(
                "allowed_bus_types",
                "Eligible vehicle categories",
                "Επιλέξιμες κατηγορίες οχημάτων",
                "types",
                True,
            ),
            C("distance_km", "Distance km", "Απόσταση χλμ.", "decimal"),
            C("is_active", "Active", "Ενεργό", "boolean"),
        ),
    ),
    "pairings": (
        "Pairings",
        "Ζεύγη",
        (
            C("service_date", "Service date", "Ημερομηνία υπηρεσίας", "date", True),
            C("driver_ref", "Staff reference", "Κωδικός οδηγού", "reference", True),
            C(
                "vehicle_ref",
                "Vehicle reference",
                "Κωδικός οχήματος",
                "reference",
                True,
            ),
            C("home_station", "Starting base", "Αρχική έδρα", required=True),
        ),
    ),
    "connections": (
        "Connections", "Συνδέσεις δρομολογίων",
        (C("incoming_ref", "Incoming trip reference", "Κωδικός προηγούμενου δρομολογίου", "reference", True),
         C("outgoing_ref", "Following trip reference", "Κωδικός επόμενου δρομολογίου", "reference", True),
         C("is_active", "Active", "Ενεργή", "boolean")),
    ),
    "transfers": (
        "Travel times",
        "Χρόνοι μετακίνησης",
        (
            C("origin", "Origin station", "Σταθμός αναχώρησης", required=True),
            C("destination", "Destination station", "Σταθμός άφιξης", required=True),
            C("minutes", "Minutes", "Λεπτά", "integer", True),
            C("source_note", "Source note", "Σημείωση πηγής"),
        ),
    ),
}
WEEKDAYS = {
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    "el": ("Δευ", "Τρι", "Τετ", "Πεμ", "Παρ", "Σαβ", "Κυρ"),
}
ARRIVAL_DAYS = {
    "en": ("Same day", "Next day", "Two days later"),
    "el": ("Ίδια ημέρα", "Επόμενη ημέρα", "Μετά από δύο ημέρες"),
}


def title(entity, locale):
    return SHEETS[entity][1 if locale == "el" else 0]
