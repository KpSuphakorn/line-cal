# Domain notes

The core aggregate is a LINE user with owned food entries, workout programs and
workout sessions. API callers must not select an owner; the authenticated identity selects
the owner. LINE webhooks are trusted only after HMAC signature verification.

AI nutrition values are estimates and remain editable by the user. Confirmation
and edit links must carry an opaque record/token, never a user ID.
