# LINE Cal product completion plan

## Product boundary

LINE Cal is a small multi-user pilot for recording food and exercise through
LINE. LINE is the fast capture interface; the LIFF Web App owns editing,
history, workout-program management and profile settings. Supabase PostgreSQL is
the production source of truth.

The product must remain useful for three to five users without adding an admin
portal, complex timers or duplicate entry points.

## Canonical user journeys

### 1. Onboarding

1. A user adds the LINE Official Account.
2. The bot requires profile setup before any logging action.
3. LIFF verifies the LINE Login ID token and opens Profile.
4. The user enters display name, birth date/age, sex used by the calorie formula,
   height, weight, goal and activity level.
5. The app suggests calorie and protein targets; the user may override them.
6. Push, Pull and Legs templates are copied into user-owned workout programs.

There is no allowlist. Identity always comes from a signed LINE webhook event or
a server-verified LIFF ID token, never from a URL parameter.

### 2. Food capture

Both entry points share one flow:

- Send a food image.
- Send `กิน <description>`, for example `กิน ข้าวมันไก่ไม่เอาหนัง`.
- Separate typed items with `+`, for example `กิน ข้าวมันไก่ + น้ำส้ม`.

A capture holds one or more independent food analysis drafts. A photo is split
by plate/bowl/glass, not by ingredient: rice, chicken and egg on one plate is
one draft, a plate plus a separate drink is two. Typed text is split only
where the user wrote `+`: one dish stays one draft, named as typed, rather
than being broken into its components. The response offers:

- Edit items in LIFF.
- Confirm all items.
- Cancel the capture.

The draft editor can add, remove or edit name, portion, calories, protein,
carbohydrate and fat for every item. Confirmation creates separate Food Entries
with a common capture reference. Confirmed entries remain editable and
deletable from Today and History.

Images are analyzed transiently and are not retained in the MVP. Store the
source type and AI metadata, not the image bytes.

### 3. Strength workout

1. The user sends `เวท` or taps เวท in the Rich Menu.
2. A card shows the user's Push, Pull, Legs and custom programs plus Cardio.
3. Selecting a strength program immediately records a Workout Session snapshot.
4. The user may edit the recorded exercises afterward without changing the
   source program.

Each program exercise stores only:

- Name
- Sets
- Repetitions
- Weight
- Notes

No timer is required. Estimate session duration from the saved program:

```text
work seconds = sets × repetitions × 3 seconds
between-set rest = max(sets - 1, 0) × 60 seconds
between-exercise rest = max(exercise count - 1, 0) × 120 seconds
estimated duration = sum(work seconds + between-set rest) + between-exercise rest
```

Estimate strength calories at the session level, not per exercise:

```text
kcal = MET × 3.5 × body_weight_kg / 200 × estimated_minutes
```

Use a conservative resistance-training MET default and label the result
“estimated”. Lifted weight remains progression data because it cannot identify
relative effort without the user's one-repetition maximum, tempo and actual
rest. The final calorie estimate remains editable.

### 4. Cardio

Cardio uses the same reusable-program flow as strength. The user creates a
cardio preset once, then selects that saved preset from the `เวท` entry
point to record a session. Presets are named after the activity and contain
only the fields needed for that activity, such as duration, incline and speed
for incline walking or duration and pace/distance for running. Calories use the
activity MET, body weight and the preset duration. There is no one-off cardio
recording form; an existing session can still be edited afterward.

### 5. Daily balance

Display four values independently:

- Food consumed
- Daily food target
- Exercise energy estimate
- Net energy for information

Exercise never automatically raises the user's food target. Avoid language such
as “earned calories” or “you can eat more”.

## Chat contract

| Input | Behaviour |
| --- | --- |
| Food image | Create one or more editable food analysis drafts |
| `กิน <description>` | Enter the same draft flow as a food image |
| `สรุป` | Show today's food, exercise and net summary |
| `เวท` | Show saved strength programs and cardio presets as individual cards |
| `ประวัติ` | Open LIFF History |
| `วิธีใช้` | Show only the supported commands |

Unknown text returns the command guide. It must not call a general nutrition
question-answering model.

## Information architecture

### LIFF Web App

Use one bottom navigation with four destinations:

1. **Today** — daily summary and editable Food Entries/Workout Sessions.
2. **History** — calendar, daily detail and monthly summaries.
3. **Programs** — create, edit, reorder and delete user-owned workout programs.
4. **Profile** — required body data, goal, activity level and target overrides.

Analytics belongs inside History; it is not a fifth tab. Do not render a second
top tab bar.

### Rich Menu

Use a single 3×2 default menu:

1. Camera
2. Today
3. เวท
4. History
5. Profile
6. Help

Use LINE Official Account Manager as the owner of this menu. Do not also manage
the same menu with the Messaging API script.

## Remove or consolidate

Delete these product surfaces rather than maintaining aliases:

- Quick Snacks and all banana, milk, matcha and nut shortcuts.
- The Quick Snacks Flex card and postback handlers.
- General nutrition Q&A and its fallback Gemini call.
- Direct `Day 1`–`Day 4` and hard-coded Push/Pull/Lower/Upper logging branches.
- The `meal_type` breakfast/lunch/dinner/snack concept.
- Hard-coded personal body metrics and Suphakorn-specific README examples.
- Duplicate top navigation and duplicated Web App actions.
- Hard-coded workout choices in the workout modal.
- `scripts/setup_rich_menu.py` after the menu is recreated in Official Account
  Manager.
- Legacy user-ID path APIs after LIFF has migrated fully to `/api/me/*`.
- One of the two Gemini SDK dependencies; keep only the SDK used by the final AI
  adapter.

Keep one command-guide card because users need to discover `กิน`, `สรุป` and
`เวท`.

## Relational data model

### Identity and profile

- `users`: LINE subject, display name, birth date/age, calculation sex, height,
  weight, goal, activity level, targets, timezone and onboarding status.

### Food

- `food_captures`: user, source (`image` or `text`), LINE message/event ID,
  status, timestamps and expiry.
- `food_analysis_drafts`: capture, suggested name/portion/macros, confidence and
  ordering.
- `food_entries`: confirmed user-owned values, capture reference and consumed
  timestamp.

Confirmation consumes a capture atomically. LINE redelivery or double taps must
not create duplicate entries.

### Exercise

- `program_templates`: system Push, Pull and Legs templates.
- `template_exercises`: exercises belonging to a template.
- `workout_programs`: user-owned copies and custom programs.
- `program_exercises`: name, sets, repetitions, weight, notes and order.
- `workout_sessions`: user, selected program snapshot/name, strength/cardio
  type, estimated duration, estimated calories and performed timestamp.
- `session_exercises`: the exercise snapshot editable independently of the
  program.
- `cardio_details`: activity, duration and optional incline/speed/distance.

Use foreign keys, non-null ownership, non-negative checks and indexes beginning
with `(user_id, occurred_at)` where history queries need them.

### AI quota

Do not add a quota table for the pilot. Count the user's food captures that
actually called the model (`used_ai`) within the Bangkok day and compare it with
`AI_DAILY_LIMIT`, default 60. A capture served from the food estimate cache
spends nothing and is not counted. Manual editing, history and exercise remain
unlimited.

## Delivery slices

### Slice 1 — Remove dead surfaces

Remove Quick Snacks, nutrition Q&A, hard-coded workout logging, duplicated
navigation, stale commands and personal defaults. Update the guide and README.

### Slice 2 — Profile gate and user templates

Require onboarding, finish the profile schema and copy Push/Pull/Leg templates
into separate user-owned programs.

### Slice 3 — Unified food capture

Create multi-item drafts for image and `กิน` input, build the LIFF draft editor,
confirm atomically and support historical edits.

### Slice 4 — Programs and sessions

Replace the current split representation with programs, exercises, session
snapshots and one-tap completion. Add automatic strength duration/calorie
estimates.

### Slice 5 — Cardio presets and daily balance

Add reusable cardio presets and activity MET estimates. Present food target,
exercise and net values separately.

### Slice 6 — Final UI and LINE surfaces

Reduce LIFF to four bottom tabs, update Flex cards and configure the six-action
Rich Menu in Official Account Manager.

### Slice 7 — Supabase cutover

Create the Supabase project, apply Alembic to an empty database, configure the
runtime connection and only then migrate disposable pilot data if it is still
needed.

Feature implementation comes before broad regression testing, as requested.
Each slice must still remain runnable; the full independent test/review gate is
performed after the feature slices are complete and before production release.

## Completion criteria

- A new user cannot log data before completing Profile.
- Every user receives independent Push/Pull/Leg programs.
- Image and `กิน` inputs create the same editable multi-item draft.
- Confirmed food items and workout sessions can be edited later.
- Strength logging requires one tap and no timer.
- Cardio is recorded by selecting a saved cardio preset; the preset captures the
  required duration and activity-specific fields.
- Quick Snacks, general Q&A and direct Day shortcuts no longer exist.
- LIFF has exactly four bottom destinations and no duplicate navigation.
- The Rich Menu has the agreed six actions.
- Production data is stored in Supabase PostgreSQL with migrations applied.

## References

- [2024 Compendium conditioning activities](https://pacompendium.com/conditioning-exercise/)
- [Supabase database connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [LINE Rich Menu overview](https://developers.line.biz/en/docs/messaging-api/rich-menus-overview/)
