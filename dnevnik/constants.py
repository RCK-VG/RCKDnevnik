# Labels for the two student flags. Change these two lines to rename the
# badges shown next to student names everywhere in the app.
IP_LABEL = "IP"
PP_LABEL = "PP"
IP_FULL_NAME = "Individualizirani program"
PP_FULL_NAME = "Prilagođeni program"

ATTENDANCE_PRESENT = "prisutan"
ATTENDANCE_ABSENT = "odsutan"
ATTENDANCE_LATE = "kasni"

ATTENDANCE_STATUS_CHOICES = [
    (ATTENDANCE_PRESENT, "Prisutan"),
    (ATTENDANCE_ABSENT, "Odsutan"),
    (ATTENDANCE_LATE, "Kasni"),
]

# Highest school hour of the day that can be entered ("Sat u danu").
MAX_PERIOD = 10

# Optional split of a class into groups (e.g. a practical/lab subject taught
# to half the class at a time). Add more letters here if a school ever needs
# more than two groups - it's just a plain choices list.
GROUP_CHOICES = [
    ("A", "Grupa A"),
    ("B", "Grupa B"),
]
