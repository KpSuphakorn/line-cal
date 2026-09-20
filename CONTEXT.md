# LINE Cal context

LINE Cal is a LINE webhook plus LIFF web app for food, nutrition and workout
logging. The LINE user ID is the immutable identity (`User.id`) and is obtained
from a verified LINE Login ID token in the web app. Webhook identity comes from
the signed LINE event source.

## Language

**Food analysis draft**:
An AI suggestion produced from a food photo or chat message. A user may edit it,
confirm it as a meal, or cancel it; it is not part of nutrition history until
confirmed.
_Avoid_: Pending analysis, food log draft

**Food entry**:
A confirmed, user-owned record of one food or drink consumed at a particular
time. Entries are independent rather than grouped into breakfast, lunch or
dinner, and remain editable after confirmation.
_Avoid_: Meal, food log, meal type

**Food capture**:
The shared flow entered by either a food photo or the chat command
`กิน <description>`. AI may suggest several independent food analysis drafts
from one capture.
_Avoid_: Quick log

**Workout program**:
A user-created, reusable collection of exercises. It is not tied to a weekday;
the user chooses which program to perform when starting a workout.
_Avoid_: Weekly plan, split, workout log

**Program template**:
A system-provided Push, Pull or Legs starting point that is copied into a user's
own workout programs during onboarding. Editing the copy never changes another
user's programs.
_Avoid_: Shared program, global split

**Program exercise**:
One exercise in a workout program, defined by name, sets, repetitions, weight
and notes.
_Avoid_: Plan day exercise

**Workout session**:
What a user actually performed on a date, created from a selected workout
program or entered as cardio. It is historical data and does not modify the
program.
_Avoid_: Workout log, completed plan

**Exercise energy estimate**:
An app-generated approximation of calories burned, displayed separately from the
user's food target and editable when needed.
_Avoid_: Earned calories, calorie credit

**Cardio session**:
A workout session whose energy estimate is based on the cardio activity, the
user's body weight and a duration entered by the user.
_Avoid_: Cardio program

**Bangkok day**:
A calendar day in `Asia/Bangkok`; persisted event times are UTC.

## Storage decision

Supabase/PostgreSQL remains the production database. The relational model fits
ownership, food/workout history and idempotency constraints; SQLite is a local
development fallback only.
